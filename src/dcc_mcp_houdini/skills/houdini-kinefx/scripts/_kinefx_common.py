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
    geo = get_geo_container(hou, geo_path)

    # Check if rig already exists.
    existing = hou.node("{}/{}".format(geo.path(), rig_name))
    if existing is not None:
        return existing

    # Create a KineFX skeleton by building a line of points with joint attrs.
    # We use a 'bonedeform' as the main rig anchor and create joints via
    # SOP chain.
    rig_sop = geo.createNode("null", node_name=rig_name)

    if joint_chain:
        # Build skeleton using a chain of points.
        points_positions = []
        joint_names = []
        for joint in joint_chain:
            if isinstance(joint, dict):
                name = joint.get("name", "joint")
                pos = joint.get("translate", [0, 0, 0])
            elif isinstance(joint, (list, tuple)):
                name = str(joint[0]) if len(joint) > 0 else "joint"
                pos = list(joint[2]) if len(joint) > 2 else [0, 0, 0]
            else:
                name = str(joint)
                pos = [0, 0, 0]
            joint_names.append(name)
            points_positions.append(list(pos))

        if points_positions:
            # Create geometry with skeleton attributes.
            rig_geo = rig_sop.geometry()
            rig_geo.clear()
            pts = rig_geo.createPoints(len(points_positions))
            name_attr = rig_geo.addAttrib(hou.attribType.Point, "name", "")
            for i, pt in enumerate(pts):
                pt.setPosition(points_positions[i])
                pt.setAttribValue(name_attr, joint_names[i])

    rig_sop.moveToGoodPosition()
    return rig_sop
