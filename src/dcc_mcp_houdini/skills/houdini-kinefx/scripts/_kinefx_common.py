"""Shared helpers for Houdini KineFX skills.

Cook validation and capability gating live here so every scene tool uses the
same discipline. This module imports no ``hou`` at module scope: all host
access is through the ``hou``/``container`` arguments, so it stays importable
(and unit-testable) without a licensed Houdini.
"""

from __future__ import annotations

from typing import Any


class RequiresHoudini22(Exception):
    """A Houdini-22-only node type is unavailable on the running host.

    Raised by :func:`capability_create_node` when ``createNode`` fails with
    "Invalid node type name" for a stage-6 / APEX node type. Scene tools catch
    it and return a structured ``capability_unavailable`` error instead of an
    uncaught ``hou.OperationFailed``.
    """

    def __init__(self, node_type: str, detail: str = "") -> None:
        self.node_type = node_type
        self.detail = detail
        super().__init__("Houdini 22 node type unavailable: {}".format(node_type))


def capability_create_node(container: Any, type_name: str, name: str) -> Any:
    """Create *type_name*, translating a missing H22 node type to a capability error.

    On Houdini 20.5/21 the Motion Mixer / APEX node types do not exist; a bare
    ``createNode`` raises ``hou.OperationFailed: Invalid node type name``. We
    convert that into :class:`RequiresHoudini22` so the caller can degrade
    gracefully. All other create failures propagate unchanged.
    """
    try:
        return container.createNode(type_name, node_name=name)
    except Exception as exc:  # noqa: BLE001 - only translate missing node types
        if "Invalid node type name" in str(exc):
            raise RequiresHoudini22(type_name, str(exc)) from exc
        raise


def guarded_cook_failures(nodes: Any, force: bool = True) -> list:
    """Cook each node, recording errors as cook_failures; never raises.

    DOP data nodes and multi-input KineFX nodes are not standalone-cookable on
    20.5/21/22: ``node.cook(force=True)`` raises ``hou.OperationFailed``. A cook
    failure is a validation result, not a tool failure, so exceptions are caught
    and returned as ``cook_failures`` entries (the tool stays ``success=True``
    with ``validated=False``). ``errors()``/``warnings()`` calls are guarded too.
    """
    failures = []
    for node in nodes:
        try:
            if force:
                node.cook(force=True)
            else:
                node.cook()
        except Exception as exc:  # noqa: BLE001 - a cook error is a validation result
            failures.append({"path": node.path(), "errors": [str(exc)], "warnings": []})
            continue
        try:
            errors = [str(err) for err in node.errors()]
            warnings = [str(warn) for warn in node.warnings()]
        except Exception as exc:  # noqa: BLE001 - diagnostics must not crash the tool
            errors, warnings = [str(exc)], []
        if errors or warnings:
            failures.append({"path": node.path(), "errors": errors, "warnings": warnings})
    return failures


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def get_geo_container(hou: Any, geo_path: str) -> Any:
    """Return the geometry container at *geo_path*, ensuring it exists."""
    node = hou.node(geo_path)
    if node is not None:
        return node
    # Walk up to find parent, create geo container.
    parts = geo_path.strip("/").split("/")
    for i in range(len(parts) - 1, -1, -1):
        parent_path = "/" + "/".join(parts[: i + 1])
        parent = hou.node(parent_path)
        if parent is not None:
            for name in parts[i + 1 :]:
                parent = parent.createNode("geo", node_name=name)
            return parent
    raise ValueError("Cannot resolve geometry path: {}".format(geo_path))


def get_or_create_rig(
    hou: Any,
    geo_path: str,
    rig_name: str,
    joint_chain: list | None = None,
) -> Any:
    """Return or create a KineFX rig node inside *geo_path*.

    If *joint_chain* is provided, creates a skeleton from joint definitions.
    Each joint is ``[name, parent_index, translate]``.
    """
    if not isinstance(geo_path, str) or not geo_path.strip():
        raise ValueError("geo_path must be a non-empty string")
    if not isinstance(rig_name, str) or not rig_name.strip():
        raise ValueError("rig_name must be a non-empty string")

    points_positions = []
    joint_names = []
    parent_indices = []
    for index, joint in enumerate(joint_chain or []):
        if isinstance(joint, dict):
            name = joint.get("name", "joint")
            pos = joint.get("translate", [0, 0, 0])
            parent_index = joint.get("parent_index", index - 1)
        elif isinstance(joint, (list, tuple)):
            name = str(joint[0]) if len(joint) > 0 else "joint"
            parent_index = joint[1] if len(joint) > 1 else index - 1
            pos = list(joint[2]) if len(joint) > 2 else [0, 0, 0]
        else:
            name = str(joint)
            parent_index = index - 1
            pos = [0, 0, 0]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Joint name must be a non-empty string")
        parent_index = int(parent_index)
        if parent_index < -1 or parent_index >= index:
            raise ValueError("Joint {!r} parent_index must reference an earlier joint or -1".format(name))
        if len(pos) != 3:
            raise ValueError("Joint {!r} translate must contain exactly 3 values".format(name))
        if name in joint_names:
            raise ValueError("Joint names must be unique: {!r}".format(name))
        joint_names.append(name)
        parent_indices.append(parent_index)
        points_positions.append([float(value) for value in pos])

    geo = get_geo_container(hou, geo_path)

    # Check if rig already exists.
    existing = hou.node("{}/{}".format(geo.path(), rig_name))
    if existing is not None:
        return existing

    rig_sop = geo.createNode("kinefx::skeleton", node_name=rig_name)

    if points_positions:
        rig_geo = hou.Geometry()
        pts = rig_geo.createPoints(points_positions)
        name_attr = rig_geo.addAttrib(hou.attribType.Point, "name", "")
        transform_attr = rig_geo.addAttrib(
            hou.attribType.Point,
            "transform",
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        )
        for i, pt in enumerate(pts):
            pt.setPosition(points_positions[i])
            pt.setAttribValue(name_attr, joint_names[i])
            pt.setAttribValue(
                transform_attr,
                (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            )
        for child_index, parent_index in enumerate(parent_indices):
            if parent_index < 0:
                continue
            bone = rig_geo.createPolygon()
            bone.setIsClosed(False)
            bone.addVertex(pts[parent_index])
            bone.addVertex(pts[child_index])

        stash = rig_sop.parm("stash")
        if stash is None:
            raise RuntimeError("KineFX Skeleton node has no stash parameter")
        stash.set(rig_geo)
        rig_sop.cook(force=True)

    rig_sop.moveToGoodPosition()
    return rig_sop
