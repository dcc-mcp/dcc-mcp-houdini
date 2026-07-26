"""Shared helpers for Houdini KineFX skills."""

from __future__ import annotations

from typing import Any


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
