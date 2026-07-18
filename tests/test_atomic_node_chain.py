"""Behaviour tests for atomic structured Houdini node-chain builds."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest
from skill_loader import skill_script_import_context

_SCRIPT = (
    Path(__file__).parent.parent
    / "src"
    / "dcc_mcp_houdini"
    / "skills"
    / "houdini-automation"
    / "scripts"
    / "build_node_chain.py"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("skill_atomic_build_node_chain", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class FakeNodeType:
    def __init__(self, name: str, max_inputs: int, max_outputs: int) -> None:
        self._name = name
        self._max_inputs = max_inputs
        self._max_outputs = max_outputs

    def name(self) -> str:
        return self._name

    def maxNumInputs(self) -> int:
        return self._max_inputs

    def maxNumOutputs(self) -> int:
        return self._max_outputs


class FakeCategory:
    def __init__(self, node_types: Dict[str, FakeNodeType]) -> None:
        self._node_types = node_types

    def nodeTypes(self) -> Dict[str, FakeNodeType]:
        return dict(self._node_types)


class FakeParm:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.value: Any = None

    def set(self, value: Any) -> None:
        if self.fail:
            raise RuntimeError("parameter write failed")
        self.value = value


class FakeConnection:
    def __init__(
        self,
        input_index: int,
        source: "FakeNode",
        destination: "FakeNode",
        output_index: int,
    ) -> None:
        self._input_index = input_index
        self._source = source
        self._destination = destination
        self._output_index = output_index

    def inputIndex(self) -> int:
        return self._input_index

    def inputNode(self) -> "FakeNode":
        if isinstance(self._source, FakeIndirectInput):
            return self._source.upstream
        return self._source

    def inputItem(self) -> Any:
        return self._source

    def inputItemOutputIndex(self) -> int:
        return self._output_index

    def outputNode(self) -> "FakeNode":
        return self._destination

    def outputIndex(self) -> int:
        return self._output_index


class FakeIndirectInput:
    def __init__(self, path: str, upstream: Optional["FakeNode"] = None) -> None:
        self._path = path
        self.upstream = upstream

    def path(self) -> str:
        return self._path


class FakeNode:
    def __init__(
        self,
        parent: "FakeParent",
        node_type: FakeNodeType,
        name: str,
        *,
        position: Tuple[float, float] = (0.0, 0.0),
        failing_parms: Optional[List[str]] = None,
        cook_fails: bool = False,
    ) -> None:
        self._parent = parent
        self._type = node_type
        self._name = name
        self._position = position
        self._inputs: Dict[int, Tuple[FakeNode, int]] = {}
        self._parms: Dict[str, FakeParm] = {}
        self._failing_parms = set(failing_parms or [])
        self._cook_fails = cook_fails
        self.cooked = False
        self.destroyed = False

    def name(self) -> str:
        return self._name

    def path(self) -> str:
        if self.destroyed:
            raise RuntimeError("ObjectWasDeleted")
        return "{}/{}".format(self._parent.path().rstrip("/"), self._name)

    def parent(self) -> "FakeParent":
        return self._parent

    def type(self) -> FakeNodeType:
        return self._type

    def parm(self, name: str) -> FakeParm:
        if name not in self._parms:
            self._parms[name] = FakeParm(fail=name in self._failing_parms)
        return self._parms[name]

    def parmTuple(self, name: str) -> None:
        return None

    def setInput(self, input_index: int, source: Optional["FakeNode"], output_index: int = 0) -> None:
        if source is None:
            self._inputs.pop(input_index, None)
        else:
            self._inputs[input_index] = (source, output_index)

    def inputConnections(self) -> Tuple[FakeConnection, ...]:
        return tuple(
            FakeConnection(input_index, source, self, output_index)
            for input_index, (source, output_index) in sorted(self._inputs.items())
        )

    def position(self) -> Tuple[float, float]:
        return self._position

    def setPosition(self, position: Tuple[float, float]) -> None:
        self._position = position

    def cook(self, force: bool = False) -> None:
        del force
        if self._cook_fails:
            raise RuntimeError("cook failed")
        self.cooked = True

    def errors(self) -> Tuple[str, ...]:
        return ()

    def warnings(self) -> Tuple[str, ...]:
        return ()

    def destroy(self) -> None:
        self.destroyed = True
        self._parent.remove(self)


class FakeParent:
    def __init__(self, path: str = "/obj/geo1") -> None:
        self._path = path
        self.editable = True
        self.types = {
            "box": FakeNodeType("box", 0, 1),
            "mtlxdisplacement": FakeNodeType("mtlxdisplacement", 1, 1),
            "mtlximage": FakeNodeType("mtlximage", 0, 1),
            "mtlxrange": FakeNodeType("mtlxrange", 1, 1),
            "null": FakeNodeType("null", 4, 1),
            "rendergeometrysettings": FakeNodeType("rendergeometrysettings", 1, 1),
        }
        self._children: List[FakeNode] = []
        self.create_count = 0
        self.exact_type_name_values: List[bool] = []
        self.layout_count = 0
        self.failing_parms: Dict[str, List[str]] = {}
        self.cook_fail_names: set = set()
        self.external_nodes: Dict[str, FakeNode] = {}

    def path(self) -> str:
        return self._path

    def isNetwork(self) -> bool:
        return True

    def isEditable(self) -> bool:
        return self.editable

    def childTypeCategory(self) -> FakeCategory:
        return FakeCategory(self.types)

    def children(self) -> Tuple[FakeNode, ...]:
        return tuple(self._children)

    def createNode(
        self,
        node_type: str,
        node_name: Optional[str] = None,
        exact_type_name: bool = False,
    ) -> FakeNode:
        self.create_count += 1
        self.exact_type_name_values.append(exact_type_name)
        name = node_name or "{}{}".format(node_type, self.create_count)
        node = FakeNode(
            self,
            self.types[node_type],
            name,
            failing_parms=self.failing_parms.get(name),
            cook_fails=name in self.cook_fail_names,
        )
        self._children.append(node)
        return node

    def add_existing(
        self,
        node_type: str,
        name: str,
        position: Tuple[float, float],
    ) -> FakeNode:
        node = FakeNode(self, self.types[node_type], name, position=position)
        self._children.append(node)
        return node

    def remove(self, node: FakeNode) -> None:
        self._children.remove(node)

    def node(self, ref: str) -> Optional[FakeNode]:
        if ref in self.external_nodes:
            return self.external_nodes[ref]
        normalized = ref.rsplit("/", 1)[-1]
        return next((child for child in self._children if child.name() == normalized), None)

    def layoutChildren(self) -> None:
        self.layout_count += 1
        for index, child in enumerate(self._children):
            child.setPosition((100.0 + index, 200.0))


class FakeUndoGroup:
    def __init__(self, owner: "FakeUndos", label: str) -> None:
        self.owner = owner
        self.label = label

    def __enter__(self) -> "FakeUndoGroup":
        self.owner.entered.append(self.label)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        del exc_type, exc, traceback
        self.owner.exited.append(self.label)
        if self.owner.raise_on_exit:
            raise RuntimeError("undo group exit failed")
        return False


class FakeUndos:
    def __init__(self) -> None:
        self.entered: List[str] = []
        self.exited: List[str] = []
        self.raise_on_exit = False

    def group(self, label: str) -> FakeUndoGroup:
        return FakeUndoGroup(self, label)


class FakeText:
    @staticmethod
    def variableName(value: str, safe_chars: str = "") -> str:
        normalized = "".join(
            character
            if character.isascii() and (character.isalnum() or character == "_" or character in safe_chars)
            else "_"
            for character in value
        )
        if normalized and (normalized[0].isdigit() or normalized[0] in safe_chars):
            normalized = "_" + normalized
        return normalized


class FakeHou:
    def __init__(self, parent: FakeParent) -> None:
        self.parent = parent
        self.undos = FakeUndos()
        self.text = FakeText()

    def node(self, path: str) -> Optional[Any]:
        if path == self.parent.path():
            return self.parent
        return self.parent.node(path)


def test_dry_run_validates_without_mutating_or_opening_undo_group() -> None:
    module = _load_script()
    parent = FakeParent()
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            "/obj/geo1",
            [
                {"node_type": "box", "node_name": "box1"},
                {"node_type": "null", "node_name": "OUT"},
            ],
            [{"input": "OUT", "output": "box1"}],
            dry_run=True,
        )

    assert result["success"] is True
    assert result["context"]["dry_run"] is True
    assert result["context"]["validated"]["valid"] is True
    assert result["context"]["validated"]["node_count"] == 2
    assert result["context"]["validated"]["connection_count"] == 1
    assert result["context"]["readback"] == {"performed": False}
    assert result["context"]["transaction_id"]
    assert result["context"]["undo_label"].startswith("DCC MCP: build_node_chain ")
    assert parent.create_count == 0
    assert hou.undos.entered == []


def test_prevalidation_reports_all_recipe_errors_with_zero_scene_changes() -> None:
    module = _load_script()
    parent = FakeParent()
    parent.add_existing("null", "taken", (1.0, 2.0))
    hou = FakeHou(parent)
    before = tuple(parent.children())

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            "/obj/geo1",
            [
                {"node_type": "missing", "node_name": "taken"},
                {"node_type": "null", "node_name": "dup", "ref": "same"},
                {"node_type": "null", "node_name": "dup2", "ref": "same"},
            ],
            [
                {"input": "unknown", "output": "same"},
                {"input": "dup", "output": "same", "input_index": 99},
            ],
        )

    assert result["success"] is False
    validated = result["context"]["validated"]
    assert validated["valid"] is False
    fields = {error["field"] for error in validated["errors"]}
    assert "nodes[0].node_type" in fields
    assert "nodes[0].node_name" in fields
    assert "nodes[2].ref" in fields
    assert "connections[0].input" in fields
    assert "connections[1].input_index" in fields
    assert tuple(parent.children()) == before
    assert parent.create_count == 0
    assert parent.layout_count == 0
    assert hou.undos.entered == []
    assert result["context"]["rollback"]["attempted"] is False


def test_prevalidation_rejects_existing_nodes_from_another_network() -> None:
    module = _load_script()
    parent = FakeParent()
    other_parent = FakeParent("/obj/geo2")
    external_target = other_parent.add_existing("null", "target", (0.0, 0.0))
    parent.external_nodes[external_target.path()] = external_target
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            parent.path(),
            [{"node_type": "box", "node_name": "source"}],
            [{"input": external_target.path(), "output": "source"}],
            dry_run=True,
        )

    assert result["success"] is False
    errors = result["context"]["validated"]["errors"]
    assert any(error["field"] == "connections[0].input" for error in errors)
    assert parent.create_count == 0
    assert hou.undos.entered == []


def test_prevalidation_rejects_node_names_houdini_would_normalize() -> None:
    module = _load_script()
    parent = FakeParent()
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            parent.path(),
            [{"node_type": "box", "node_name": "bad name"}],
            dry_run=True,
        )

    assert result["success"] is False
    errors = result["context"]["validated"]["errors"]
    assert any(error["field"] == "nodes[0].node_name" for error in errors)
    assert parent.create_count == 0
    assert hou.undos.entered == []


def test_prevalidation_refuses_explicit_names_without_hom_name_validator() -> None:
    module = _load_script()
    parent = FakeParent()
    hou = FakeHou(parent)
    hou.text = None

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            parent.path(),
            [{"node_type": "box", "node_name": "box1"}],
            dry_run=True,
        )

    assert result["success"] is False
    errors = result["context"]["validated"]["errors"]
    assert any(
        error["field"] == "nodes[0].node_name" and "hou.text.variableName" in error["message"] for error in errors
    )
    assert parent.create_count == 0


def test_prevalidation_rejects_uneditable_parent_network() -> None:
    module = _load_script()
    parent = FakeParent()
    parent.editable = False
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            parent.path(),
            [{"node_type": "box", "node_name": "box1"}],
            dry_run=True,
        )

    assert result["success"] is False
    errors = result["context"]["validated"]["errors"]
    assert any(error["field"] == "parent_path" and "editable" in error["message"] for error in errors)
    assert parent.create_count == 0
    assert hou.undos.entered == []


def test_parameter_failure_deletes_every_created_node_and_reports_rollback() -> None:
    module = _load_script()
    parent = FakeParent()
    parent.failing_parms["bad"] = ["explode"]
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            "/obj/geo1",
            [
                {"node_type": "box", "node_name": "good"},
                {
                    "node_type": "null",
                    "node_name": "bad",
                    "parameters": {"explode": 1},
                },
            ],
            layout=False,
            cook_last=False,
        )

    assert result["success"] is False
    assert parent.children() == ()
    assert len(hou.undos.entered) == 1
    assert hou.undos.entered == hou.undos.exited
    rollback = result["context"]["rollback"]
    assert rollback["attempted"] is True
    assert rollback["complete"] is True
    assert rollback["created_paths"] == ["/obj/geo1/good", "/obj/geo1/bad"]
    assert rollback["deleted_paths"] == ["/obj/geo1/bad", "/obj/geo1/good"]
    assert rollback["restored_connections"] == []
    assert rollback["restored_positions"] == []
    assert rollback["errors"] == []


def test_undo_exit_failure_can_repeat_rollback_after_nodes_were_destroyed() -> None:
    module = _load_script()
    parent = FakeParent()
    parent.failing_parms["bad"] = ["explode"]
    hou = FakeHou(parent)
    hou.undos.raise_on_exit = True

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            parent.path(),
            [{"node_type": "box", "node_name": "bad", "parameters": {"explode": 1}}],
            layout=False,
            cook_last=False,
        )

    assert result["success"] is False
    assert parent.children() == ()
    rollback = result["context"]["rollback"]
    assert rollback["attempted"] is True
    assert rollback["complete"] is True
    assert rollback["deleted_paths"] == ["/obj/geo1/bad"]
    assert rollback["errors"] == []


def test_cook_failure_restores_existing_connection_and_layout_positions() -> None:
    module = _load_script()
    parent = FakeParent()
    old_source = parent.add_existing("box", "old_source", (3.0, 4.0))
    target = parent.add_existing("null", "target", (8.0, 9.0))
    target.setInput(0, old_source, 0)
    parent.cook_fail_names.add("new_source")
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            "/obj/geo1",
            [{"node_type": "box", "node_name": "new_source"}],
            [{"input": "target", "output": "new_source", "input_index": 0}],
            layout=True,
            cook_last=True,
        )

    assert result["success"] is False
    assert tuple(node.name() for node in parent.children()) == ("old_source", "target")
    restored = target.inputConnections()
    assert len(restored) == 1
    assert restored[0].inputNode() is old_source
    assert restored[0].outputNode() is target
    assert restored[0].outputIndex() == 0
    assert old_source.position() == (3.0, 4.0)
    assert target.position() == (8.0, 9.0)
    rollback = result["context"]["rollback"]
    assert rollback["complete"] is True
    assert rollback["deleted_paths"] == ["/obj/geo1/new_source"]
    assert rollback["restored_connections"] == [
        {
            "input_path": "/obj/geo1/target",
            "input_index": 0,
            "output_path": "/obj/geo1/old_source",
            "output_index": 0,
        }
    ]
    assert {entry["path"] for entry in rollback["restored_positions"]} == {
        "/obj/geo1/old_source",
        "/obj/geo1/target",
    }


@pytest.mark.parametrize("upstream_connected", [False, True])
def test_cook_failure_restores_subnet_indirect_input(upstream_connected: bool) -> None:
    module = _load_script()
    parent = FakeParent()
    target = parent.add_existing("null", "target", (0.0, 0.0))
    outer_parent = FakeParent("/obj/outer")
    upstream = outer_parent.add_existing("box", "upstream", (0.0, 0.0)) if upstream_connected else None
    indirect = FakeIndirectInput("/obj/geo1/1", upstream=upstream)
    target.setInput(0, indirect, 0)
    parent.cook_fail_names.add("bad_cook")
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            parent.path(),
            [
                {"node_type": "box", "node_name": "new_source"},
                {"node_type": "null", "node_name": "bad_cook"},
            ],
            [{"input": "target", "output": "new_source", "input_index": 0}],
            layout=False,
            cook_last=True,
        )

    assert result["success"] is False
    restored = target.inputConnections()
    assert len(restored) == 1
    assert restored[0].inputItem() is indirect
    assert result["context"]["rollback"]["complete"] is True


def test_success_uses_one_named_undo_group_and_returns_scene_readback() -> None:
    module = _load_script()
    parent = FakeParent()
    hou = FakeHou(parent)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.build_node_chain(
            "/obj/geo1",
            [
                {"node_type": "box", "node_name": "box1", "parameters": {"size": 2.0}},
                {"node_type": "null", "node_name": "OUT"},
            ],
            [{"input": "OUT", "output": "box1", "input_index": 0, "output_index": 0}],
            layout=True,
            cook_last=True,
        )

    assert result["success"] is True
    assert parent.exact_type_name_values == [True, True]
    context = result["context"]
    assert context["transaction_id"]
    assert context["undo_label"] == hou.undos.entered[0]
    assert hou.undos.entered == [context["undo_label"]]
    assert hou.undos.exited == [context["undo_label"]]
    assert context["validated"]["valid"] is True
    assert context["affected_paths"] == ["/obj/geo1/OUT", "/obj/geo1/box1"]
    readback = context["readback"]
    assert readback["performed"] is True
    assert [node["path"] for node in readback["nodes"]] == [
        "/obj/geo1/box1",
        "/obj/geo1/OUT",
    ]
    assert readback["connections"] == [
        {
            "input_path": "/obj/geo1/OUT",
            "input_index": 0,
            "output_path": "/obj/geo1/box1",
            "output_index": 0,
            "matches": True,
        }
    ]
    connection = parent.node("OUT").inputConnections()[0]
    assert connection.inputNode() is parent.node("box1")
    assert connection.outputNode() is parent.node("OUT")
    assert readback["cook"]["performed"] is True
    assert readback["cook"]["node"]["path"] == "/obj/geo1/OUT"
    assert parent.node("OUT").cooked is True
    assert context["rollback"] == {"attempted": False, "complete": True, "errors": []}


def _materialx_displacement_recipe() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes = []
    connections = []
    for index in range(4):
        prefix = "surface_{}".format(index)
        nodes.extend(
            [
                {
                    "node_type": "mtlximage",
                    "node_name": "{}_image".format(prefix),
                    "parameters": {"signature": "default", "file": "/assets/{}_height.exr".format(prefix)},
                },
                {
                    "node_type": "mtlxrange",
                    "node_name": "{}_range".format(prefix),
                    "parameters": {
                        "signature": "default",
                        "inlow": 0.1,
                        "inhigh": 0.9,
                        "outlow": -1.0,
                        "outhigh": 1.0,
                        "doclamp": 1,
                    },
                },
                {
                    "node_type": "mtlxdisplacement",
                    "node_name": "{}_displacement".format(prefix),
                    "parameters": {"signature": "default", "scale": 0.01},
                },
            ]
        )
        connections.extend(
            [
                {"input": "{}_range".format(prefix), "output": "{}_image".format(prefix)},
                {"input": "{}_displacement".format(prefix), "output": "{}_range".format(prefix)},
            ]
        )
    return nodes, connections


def test_materialx_displacement_batch_and_stage_settings_return_summaries() -> None:
    module = _load_script()
    nodes, connections = _materialx_displacement_recipe()
    material_parent = FakeParent("/mat/displacement_batch")

    with patch.dict(sys.modules, {"hou": FakeHou(material_parent)}):
        material_result = module.build_node_chain(
            material_parent.path(),
            nodes,
            connections,
            layout=False,
            cook_last=False,
        )

    material_summary = material_result["context"]["summary"]
    assert material_summary["counts"] == {"created": 12, "connected": 8, "parameters": 40}
    assert all(connection["matches"] for connection in material_summary["connected"])
    assert len(material_summary["parameters"]) == 12

    stage_parent = FakeParent("/stage")
    upstream = stage_parent.add_existing("null", "upstream", (0.0, 0.0))
    downstream = stage_parent.add_existing("null", "downstream", (1.0, 0.0))
    with patch.dict(sys.modules, {"hou": FakeHou(stage_parent)}):
        settings_result = module.build_node_chain(
            stage_parent.path(),
            [
                {
                    "node_type": "rendergeometrysettings",
                    "node_name": "displacement_settings",
                    "parameters": {
                        "primpattern": "/asset/*",
                        "xn__primvarskarmaobjecttruedisplace_control_n4bfg": "set",
                        "xn__primvarskarmaobjecttruedisplace_mrbfg": "True Displacement",
                        "xn__primvarskarmaobjectdicingquality_control_95bfg": "set",
                        "xn__primvarskarmaobjectdicingquality_8sbfg": 1.25,
                    },
                }
            ],
            [
                {"input": "displacement_settings", "output": upstream.path()},
                {"input": downstream.path(), "output": "displacement_settings"},
            ],
            layout=False,
            cook_last=False,
        )

    assert settings_result["context"]["summary"]["counts"] == {
        "created": 1,
        "connected": 2,
        "parameters": 5,
    }


def test_materialx_batch_failure_leaves_no_partial_network() -> None:
    module = _load_script()
    nodes, connections = _materialx_displacement_recipe()
    parent = FakeParent("/mat/displacement_batch")
    parent.cook_fail_names.add("surface_3_displacement")

    with patch.dict(sys.modules, {"hou": FakeHou(parent)}):
        result = module.build_node_chain(
            parent.path(),
            nodes,
            connections,
            layout=False,
            cook_last=True,
        )

    assert result["success"] is False
    assert parent.children() == ()
    rollback = result["context"]["rollback"]
    assert rollback["complete"] is True
    assert len(rollback["created_paths"]) == 12
    assert set(rollback["deleted_paths"]) == set(rollback["created_paths"])
