"""Validation and transaction data for structured node-chain builds.

This module deliberately contains no MCP response formatting.  It models and
validates a recipe against the live parent network before the caller is allowed
to mutate Houdini.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


class NodeChainValidationError(ValueError):
    """Raised when a recipe cannot be executed without partial mutation."""

    def __init__(self, errors: Sequence[Dict[str, Any]]) -> None:
        super().__init__("Node-chain validation failed")
        self.errors = list(errors)


class NodeChainExecutionError(RuntimeError):
    """Execution failed after mutation began and an explicit rollback ran."""

    def __init__(
        self,
        cause: BaseException,
        rollback: Dict[str, Any],
        affected_paths: Sequence[str],
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.rollback = rollback
        self.affected_paths = list(affected_paths)


@dataclass(frozen=True)
class PlannedNode:
    index: int
    node_type: str
    node_type_object: Any
    node_name: Optional[str]
    reference: str
    parameters: Dict[str, Any]
    aliases: Tuple[str, ...]
    predicted_path: str


@dataclass(frozen=True)
class NodeReference:
    value: str
    planned_index: Optional[int] = None
    existing_node: Any = None

    @property
    def is_planned(self) -> bool:
        return self.planned_index is not None

    def identity(self) -> Tuple[str, Any]:
        if self.is_planned:
            return ("planned", self.planned_index)
        return ("existing", self.existing_node.path())


@dataclass(frozen=True)
class PlannedConnection:
    index: int
    input_ref: NodeReference
    output_ref: NodeReference
    input_index: int
    output_index: int


@dataclass(frozen=True)
class NodeChainPlan:
    parent: Any
    nodes: Tuple[PlannedNode, ...]
    connections: Tuple[PlannedConnection, ...]
    layout: bool
    cook_last: bool
    existing_children: Tuple[Any, ...]

    def validated_summary(self) -> Dict[str, Any]:
        return {
            "valid": True,
            "parent_path": self.parent.path(),
            "node_count": len(self.nodes),
            "connection_count": len(self.connections),
            "node_types": sorted({node.node_type for node in self.nodes}),
            "references": [node.reference for node in self.nodes],
            "checks": [
                "parent_network",
                "parent_editable",
                "node_specs",
                "node_types",
                "unique_names_and_references",
                "connection_references_and_indices",
            ],
        }

    def predicted_affected_paths(self) -> List[str]:
        paths = [node.predicted_path for node in self.nodes]
        for connection in self.connections:
            if not connection.input_ref.is_planned:
                paths.append(connection.input_ref.existing_node.path())
        if self.layout:
            paths.extend(node.path() for node in self.existing_children)
        return sorted(set(paths))


class NodeChainValidator:
    """Compile an untrusted recipe into an immutable, executable plan."""

    def __init__(self, hou: Any) -> None:
        self._hou = hou
        self._errors: List[Dict[str, Any]] = []

    def validate(
        self,
        parent_path: str,
        nodes: Any,
        connections: Any,
        *,
        layout: bool,
        cook_last: bool,
    ) -> NodeChainPlan:
        self._errors = []
        parent = self._validate_parent(parent_path)
        if parent is None:
            raise NodeChainValidationError(self._errors)

        existing_children = tuple(parent.children())
        node_types = self._available_node_types(parent)
        planned_nodes, aliases = self._validate_nodes(
            parent,
            parent_path,
            nodes,
            node_types,
            existing_children,
        )
        planned_connections = self._validate_connections(
            parent,
            connections,
            planned_nodes,
            aliases,
        )
        if self._errors:
            raise NodeChainValidationError(self._errors)
        return NodeChainPlan(
            parent=parent,
            nodes=tuple(planned_nodes),
            connections=tuple(planned_connections),
            layout=bool(layout),
            cook_last=bool(cook_last),
            existing_children=existing_children,
        )

    def _validate_parent(self, parent_path: Any) -> Any:
        if not isinstance(parent_path, str) or not parent_path.strip():
            self._add_error("parent_path", "must be a non-empty string")
            return None
        parent = self._hou.node(parent_path)
        if parent is None:
            self._add_error("parent_path", "parent network does not exist", value=parent_path)
            return None
        try:
            if not parent.isNetwork():
                self._add_error("parent_path", "node is not a parent network", value=parent_path)
                return None
            if not parent.isEditable():
                self._add_error("parent_path", "parent network is not editable", value=parent_path)
                return None
        except Exception as exc:  # noqa: BLE001
            self._add_error("parent_path", "failed to inspect parent network", value=parent_path, detail=str(exc))
            return None
        return parent

    def _available_node_types(self, parent: Any) -> Dict[str, Any]:
        try:
            category = parent.childTypeCategory()
            node_types = category.nodeTypes() if category is not None else {}
        except Exception as exc:  # noqa: BLE001
            self._add_error("parent_path", "failed to inspect child node types", detail=str(exc))
            return {}
        if not isinstance(node_types, dict):
            self._add_error("parent_path", "child node type catalog is unavailable")
            return {}
        return node_types

    def _validate_nodes(
        self,
        parent: Any,
        parent_path: str,
        raw_nodes: Any,
        node_types: Dict[str, Any],
        existing_children: Tuple[Any, ...],
    ) -> Tuple[List[PlannedNode], Dict[str, int]]:
        if not isinstance(raw_nodes, list) or not raw_nodes:
            self._add_error("nodes", "must be a non-empty array")
            return [], {}

        existing_names = {node.name() for node in existing_children}
        existing_paths = {node.path() for node in existing_children}
        aliases: Dict[str, int] = {}
        names: Dict[str, int] = {}
        planned: List[PlannedNode] = []

        for index, raw in enumerate(raw_nodes):
            field = "nodes[{}]".format(index)
            if not isinstance(raw, dict):
                self._add_error(field, "must be an object")
                continue
            node_type = raw.get("node_type")
            if not isinstance(node_type, str) or not node_type.strip():
                self._add_error("{}.node_type".format(field), "must be a non-empty string")
                continue
            node_type = node_type.strip()
            type_object = node_types.get(node_type)
            if type_object is None:
                self._add_error(
                    "{}.node_type".format(field),
                    "node type is not available in the parent network",
                    value=node_type,
                )

            node_name = raw.get("node_name")
            if node_name is not None:
                if not isinstance(node_name, str) or not node_name.strip():
                    self._add_error("{}.node_name".format(field), "must be a non-empty string")
                    node_name = None
                else:
                    node_name = node_name.strip()
                    self._validate_node_name(node_name, "{}.node_name".format(field))
                    if node_name in names:
                        self._add_error(
                            "{}.node_name".format(field),
                            "node name duplicates another planned node",
                            value=node_name,
                        )
                    if node_name in existing_names:
                        self._add_error(
                            "{}.node_name".format(field),
                            "node name already exists in the parent network",
                            value=node_name,
                        )
                    names[node_name] = index

            explicit_ref = raw.get("ref")
            if explicit_ref is not None and (not isinstance(explicit_ref, str) or not explicit_ref.strip()):
                self._add_error("{}.ref".format(field), "must be a non-empty string")
                explicit_ref = None
            reference = explicit_ref.strip() if isinstance(explicit_ref, str) else node_name
            if not reference:
                reference = "node_{}".format(index)

            parameters = raw.get("parameters") or {}
            if not isinstance(parameters, dict):
                self._add_error("{}.parameters".format(field), "must be an object")
                parameters = {}

            predicted_path = (
                "{}/{}".format(parent_path.rstrip("/"), node_name) if node_name else "planned:{}".format(reference)
            )
            node_aliases = tuple(dict.fromkeys(alias for alias in (reference, node_name, predicted_path) if alias))
            for alias in node_aliases:
                previous = aliases.get(alias)
                if previous is not None and previous != index:
                    self._add_error(
                        "{}.ref".format(field),
                        "reference is not unique",
                        value=alias,
                    )
                elif alias in existing_names or alias in existing_paths:
                    self._add_error(
                        "{}.ref".format(field),
                        "reference collides with an existing node",
                        value=alias,
                    )
                else:
                    aliases[alias] = index

            planned.append(
                PlannedNode(
                    index=index,
                    node_type=node_type,
                    node_type_object=type_object,
                    node_name=node_name,
                    reference=reference,
                    parameters=dict(parameters),
                    aliases=node_aliases,
                    predicted_path=predicted_path,
                )
            )
        return planned, aliases

    def _validate_node_name(self, node_name: str, field: str) -> None:
        text_api = getattr(self._hou, "text", None)
        variable_name = getattr(text_api, "variableName", None)
        if not callable(variable_name):
            self._add_error(
                field,
                "Houdini runtime does not expose hou.text.variableName for node-name validation",
            )
            return
        try:
            normalized = variable_name(node_name, ".-")
        except Exception as exc:  # noqa: BLE001
            self._add_error(field, "failed to validate Houdini node name", detail=str(exc))
            return
        if normalized != node_name:
            self._add_error(
                field,
                "node name is not valid in Houdini",
                value=node_name,
                normalized=normalized,
            )

    def _validate_connections(
        self,
        parent: Any,
        raw_connections: Any,
        planned_nodes: List[PlannedNode],
        aliases: Dict[str, int],
    ) -> List[PlannedConnection]:
        if raw_connections is None:
            raw_connections = []
        if not isinstance(raw_connections, list):
            self._add_error("connections", "must be an array")
            return []

        planned_by_index = {node.index: node for node in planned_nodes}
        occupied_targets = set()
        planned_connections: List[PlannedConnection] = []
        for index, raw in enumerate(raw_connections):
            field = "connections[{}]".format(index)
            if not isinstance(raw, dict):
                self._add_error(field, "must be an object")
                continue
            input_ref = self._resolve_reference(parent, raw.get("input"), aliases, "{}.input".format(field))
            output_ref = self._resolve_reference(
                parent,
                raw.get("output"),
                aliases,
                "{}.output".format(field),
            )
            input_index = self._validate_index(raw.get("input_index", 0), "{}.input_index".format(field))
            output_index = self._validate_index(
                raw.get("output_index", 0),
                "{}.output_index".format(field),
            )
            if input_ref is None or output_ref is None or input_index is None or output_index is None:
                continue

            target_key = (input_ref.identity(), input_index)
            if target_key in occupied_targets:
                self._add_error(
                    "{}.input_index".format(field),
                    "multiple connections target the same input slot",
                    value=input_index,
                )
            occupied_targets.add(target_key)
            if input_ref.identity() == output_ref.identity():
                self._add_error(field, "self-connections are not allowed")

            input_type = self._reference_type(input_ref, planned_by_index)
            output_type = self._reference_type(output_ref, planned_by_index)
            self._validate_port_range(input_type, input_index, True, "{}.input_index".format(field))
            self._validate_port_range(output_type, output_index, False, "{}.output_index".format(field))
            planned_connections.append(
                PlannedConnection(
                    index=index,
                    input_ref=input_ref,
                    output_ref=output_ref,
                    input_index=input_index,
                    output_index=output_index,
                )
            )
        return planned_connections

    def _resolve_reference(
        self,
        parent: Any,
        value: Any,
        aliases: Dict[str, int],
        field: str,
    ) -> Optional[NodeReference]:
        if not isinstance(value, str) or not value.strip():
            self._add_error(field, "must be a non-empty node reference")
            return None
        value = value.strip()
        if value in aliases:
            return NodeReference(value=value, planned_index=aliases[value])
        try:
            existing = parent.node(value)
            if existing is None and value.startswith("/"):
                existing = self._hou.node(value)
        except Exception as exc:  # noqa: BLE001
            self._add_error(field, "failed to resolve node reference", value=value, detail=str(exc))
            return None
        if existing is None:
            self._add_error(field, "node reference does not exist", value=value)
            return None
        try:
            existing_parent = existing.parent()
            parent_path = parent.path()
            existing_parent_path = existing_parent.path() if existing_parent is not None else None
        except Exception as exc:  # noqa: BLE001
            self._add_error(
                field,
                "failed to inspect node reference network",
                value=value,
                detail=str(exc),
            )
            return None
        if existing_parent_path != parent_path:
            self._add_error(
                field,
                "existing node is not a child of the parent network",
                value=value,
                parent_path=parent_path,
            )
            return None
        return NodeReference(value=value, existing_node=existing)

    def _validate_index(self, value: Any, field: str) -> Optional[int]:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            self._add_error(field, "must be a non-negative integer", value=value)
            return None
        return value

    def _reference_type(self, ref: NodeReference, planned: Dict[int, PlannedNode]) -> Any:
        if ref.is_planned:
            return planned[ref.planned_index].node_type_object
        return ref.existing_node.type()

    def _validate_port_range(self, type_object: Any, index: int, is_input: bool, field: str) -> None:
        if type_object is None:
            return
        method_name = "maxNumInputs" if is_input else "maxNumOutputs"
        method = getattr(type_object, method_name, None)
        try:
            maximum = int(method()) if callable(method) else None
        except Exception as exc:  # noqa: BLE001
            self._add_error(field, "failed to inspect node port range", detail=str(exc))
            return
        if maximum is None:
            self._add_error(field, "node type does not expose a port range")
        elif index >= maximum:
            self._add_error(
                field,
                "index is outside the node type port range",
                value=index,
                maximum=maximum,
            )

    def _add_error(self, field: str, message: str, **details: Any) -> None:
        error = {"field": field, "message": message}
        error.update(details)
        self._errors.append(error)


@dataclass(frozen=True)
class InputSnapshot:
    node: Any
    input_index: int
    source_item: Any
    output_index: int


@dataclass(frozen=True)
class PositionSnapshot:
    node: Any
    position: Any


@dataclass(frozen=True)
class NodeChainExecutionResult:
    nodes: Tuple[Any, ...]
    cooked_node: Any
    affected_paths: Tuple[str, ...]
    readback: Dict[str, Any]


class AtomicNodeChainExecutor:
    """Apply one validated plan, or explicitly restore its complete pre-state."""

    def __init__(
        self,
        hou: Any,
        parameter_setter: Callable[[Any, str, Any], None],
        node_summarizer: Callable[[Any], Dict[str, Any]],
    ) -> None:
        self._hou = hou
        self._set_parameter = parameter_setter
        self._summarize_node = node_summarizer

    def execute(self, plan: NodeChainPlan, undo_label: str) -> NodeChainExecutionResult:
        input_snapshots = self._capture_input_snapshots(plan)
        position_snapshots = self._capture_position_snapshots(plan)
        created: Dict[int, Any] = {}
        ordered: List[Any] = []
        created_paths: List[str] = []
        try:
            with self._hou.undos.group(undo_label):
                try:
                    for planned in plan.nodes:
                        node = plan.parent.createNode(
                            planned.node_type,
                            node_name=planned.node_name,
                            exact_type_name=True,
                        )
                        created[planned.index] = node
                        ordered.append(node)
                        created_paths.append(node.path())
                        for parm_name, value in planned.parameters.items():
                            self._set_parameter(node, parm_name, value)

                    for connection in plan.connections:
                        input_node = self._resolve(connection.input_ref, created)
                        output_node = self._resolve(connection.output_ref, created)
                        input_node.setInput(
                            connection.input_index,
                            output_node,
                            connection.output_index,
                        )

                    if plan.layout:
                        plan.parent.layoutChildren()

                    cooked_node = ordered[-1] if plan.cook_last and ordered else None
                    if cooked_node is not None:
                        cooked_node.cook(force=False)

                    readback = self._readback(plan, created, ordered, cooked_node)
                except Exception as exc:
                    rollback = self._rollback(
                        created=ordered,
                        created_paths=created_paths,
                        input_snapshots=input_snapshots,
                        position_snapshots=position_snapshots,
                    )
                    affected_paths = self._affected_paths(plan, created_paths)
                    raise NodeChainExecutionError(exc, rollback, affected_paths) from exc
        except NodeChainExecutionError:
            raise
        except Exception as exc:
            # Entering or leaving the undo group can itself fail.  No mutation
            # is expected on enter failure; on exit failure this second,
            # idempotent restoration is the safest available recovery path.
            rollback = self._rollback(
                created=ordered,
                created_paths=created_paths,
                input_snapshots=input_snapshots,
                position_snapshots=position_snapshots,
            )
            affected_paths = self._affected_paths(plan, created_paths)
            raise NodeChainExecutionError(exc, rollback, affected_paths) from exc

        return NodeChainExecutionResult(
            nodes=tuple(ordered),
            cooked_node=cooked_node,
            affected_paths=tuple(self._affected_paths(plan, created_paths)),
            readback=readback,
        )

    def _capture_input_snapshots(self, plan: NodeChainPlan) -> List[InputSnapshot]:
        snapshots: List[InputSnapshot] = []
        seen = set()
        for connection in plan.connections:
            if connection.input_ref.is_planned:
                continue
            node = connection.input_ref.existing_node
            key = (node.path(), connection.input_index)
            if key in seen:
                continue
            seen.add(key)
            current = self._connection_at(node, connection.input_index)
            snapshots.append(
                InputSnapshot(
                    node=node,
                    input_index=connection.input_index,
                    source_item=current.inputItem() if current is not None else None,
                    output_index=current.inputItemOutputIndex() if current is not None else 0,
                )
            )
        return snapshots

    def _capture_position_snapshots(self, plan: NodeChainPlan) -> List[PositionSnapshot]:
        if not plan.layout:
            return []
        return [PositionSnapshot(node=node, position=node.position()) for node in plan.existing_children]

    @staticmethod
    def _resolve(ref: NodeReference, created: Dict[int, Any]) -> Any:
        if ref.is_planned:
            return created[ref.planned_index]
        return ref.existing_node

    def _readback(
        self,
        plan: NodeChainPlan,
        created: Dict[int, Any],
        ordered: List[Any],
        cooked_node: Any,
    ) -> Dict[str, Any]:
        node_results = []
        for node in ordered:
            scene_node = plan.parent.node(node.name())
            if scene_node is None or scene_node.path() != node.path():
                raise RuntimeError("Created node failed scene readback: {}".format(node.path()))
            node_results.append(self._summarize_node(scene_node))

        connection_results = []
        for planned in plan.connections:
            input_node = self._resolve(planned.input_ref, created)
            output_node = self._resolve(planned.output_ref, created)
            actual = self._connection_at(input_node, planned.input_index)
            matches = bool(
                actual is not None
                and actual.inputItem() == output_node
                and actual.inputItemOutputIndex() == planned.output_index
            )
            entry = {
                "input_path": input_node.path(),
                "input_index": planned.input_index,
                "output_path": output_node.path(),
                "output_index": planned.output_index,
                "matches": matches,
            }
            connection_results.append(entry)
            if not matches:
                raise RuntimeError("Connection failed scene readback: {}".format(entry))

        cook_result = {"performed": cooked_node is not None}
        if cooked_node is not None:
            cook_result.update(
                {
                    "node": self._summarize_node(cooked_node),
                    "errors": list(cooked_node.errors()) if hasattr(cooked_node, "errors") else [],
                    "warnings": list(cooked_node.warnings()) if hasattr(cooked_node, "warnings") else [],
                }
            )
        parameter_results = [
            {
                "path": created[planned.index].path(),
                "values": dict(planned.parameters),
            }
            for planned in plan.nodes
            if planned.parameters
        ]
        summary = {
            "created": node_results,
            "connected": connection_results,
            "parameters": parameter_results,
            "counts": {
                "created": len(node_results),
                "connected": len(connection_results),
                "parameters": sum(len(entry["values"]) for entry in parameter_results),
            },
        }
        return {
            "performed": True,
            "nodes": node_results,
            "connections": connection_results,
            "cook": cook_result,
            "summary": summary,
        }

    @staticmethod
    def _connection_at(node: Any, input_index: int) -> Any:
        for connection in node.inputConnections():
            if connection.inputIndex() == input_index:
                return connection
        return None

    def _rollback(
        self,
        *,
        created: List[Any],
        created_paths: List[str],
        input_snapshots: List[InputSnapshot],
        position_snapshots: List[PositionSnapshot],
    ) -> Dict[str, Any]:
        evidence: Dict[str, Any] = {
            "attempted": True,
            "complete": True,
            "created_paths": list(created_paths),
            "deleted_paths": [],
            "restored_connections": [],
            "restored_positions": [],
            "errors": [],
        }
        for snapshot in input_snapshots:
            try:
                snapshot.node.setInput(
                    snapshot.input_index,
                    snapshot.source_item,
                    snapshot.output_index,
                )
                evidence["restored_connections"].append(
                    {
                        "input_path": snapshot.node.path(),
                        "input_index": snapshot.input_index,
                        "output_path": snapshot.source_item.path() if snapshot.source_item is not None else None,
                        "output_index": snapshot.output_index,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                evidence["errors"].append(
                    "restore connection {}[{}]: {}".format(
                        self._safe_node_path(snapshot.node),
                        snapshot.input_index,
                        exc,
                    )
                )

        for snapshot in position_snapshots:
            try:
                snapshot.node.setPosition(snapshot.position)
                evidence["restored_positions"].append(
                    {
                        "path": snapshot.node.path(),
                        "position": self._position_value(snapshot.position),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                evidence["errors"].append("restore position {}: {}".format(self._safe_node_path(snapshot.node), exc))

        for index in reversed(range(len(created))):
            node = created[index]
            path = created_paths[index] if index < len(created_paths) else None
            try:
                path = node.path()
            except Exception as exc:  # noqa: BLE001
                if path is None:
                    evidence["errors"].append("resolve created node path at index {}: {}".format(index, exc))
                    continue
            try:
                live_node = self._hou.node(path)
            except Exception as exc:  # noqa: BLE001
                evidence["errors"].append("resolve created node {}: {}".format(path, exc))
                continue
            if live_node is None:
                evidence["deleted_paths"].append(path)
                continue
            try:
                live_node.destroy()
                evidence["deleted_paths"].append(path)
            except Exception as exc:  # noqa: BLE001
                evidence["errors"].append("delete {}: {}".format(path, exc))

        self._verify_rollback(
            evidence,
            created_paths=created_paths,
            input_snapshots=input_snapshots,
            position_snapshots=position_snapshots,
        )
        evidence["complete"] = not evidence["errors"]
        return evidence

    def _verify_rollback(
        self,
        evidence: Dict[str, Any],
        *,
        created_paths: List[str],
        input_snapshots: List[InputSnapshot],
        position_snapshots: List[PositionSnapshot],
    ) -> None:
        for path in created_paths:
            try:
                if self._hou.node(path) is not None:
                    evidence["errors"].append("created node still exists after rollback: {}".format(path))
            except Exception as exc:  # noqa: BLE001
                evidence["errors"].append("verify deleted node {}: {}".format(path, exc))

        for snapshot in input_snapshots:
            try:
                actual = self._connection_at(snapshot.node, snapshot.input_index)
                actual_source_item = actual.inputItem() if actual is not None else None
                actual_output_index = actual.inputItemOutputIndex() if actual is not None else 0
                if actual_source_item != snapshot.source_item or actual_output_index != snapshot.output_index:
                    evidence["errors"].append(
                        "connection rollback verification failed: {}[{}]".format(
                            snapshot.node.path(),
                            snapshot.input_index,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                evidence["errors"].append(
                    "verify connection {}[{}]: {}".format(
                        self._safe_node_path(snapshot.node),
                        snapshot.input_index,
                        exc,
                    )
                )

        for snapshot in position_snapshots:
            try:
                if snapshot.node.position() != snapshot.position:
                    evidence["errors"].append("position rollback verification failed: {}".format(snapshot.node.path()))
            except Exception as exc:  # noqa: BLE001
                evidence["errors"].append("verify position {}: {}".format(self._safe_node_path(snapshot.node), exc))

    @staticmethod
    def _safe_node_path(node: Any) -> str:
        try:
            return str(node.path())
        except Exception:  # noqa: BLE001
            return "<deleted-or-unavailable-node>"

    @staticmethod
    def _position_value(position: Any) -> Any:
        try:
            return [float(position[0]), float(position[1])]
        except (IndexError, TypeError, ValueError):
            return str(position)

    @staticmethod
    def _affected_paths(plan: NodeChainPlan, created_paths: List[str]) -> List[str]:
        paths = list(created_paths)
        for connection in plan.connections:
            if not connection.input_ref.is_planned:
                paths.append(connection.input_ref.existing_node.path())
        if plan.layout:
            paths.extend(node.path() for node in plan.existing_children)
        return sorted(set(paths))
