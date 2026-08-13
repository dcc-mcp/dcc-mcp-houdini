"""Validate named KineFX joints against one ground surface."""

from __future__ import annotations

from typing import Iterable, List

from _kinefx_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _classify(clearance: float, tolerance: float) -> str:
    if clearance < -tolerance:
        return "penetrating"
    if abs(clearance) <= tolerance:
        return "contact"
    return "lifted"


def _object_transform(node):
    """Return the nearest OBJ transform, or ``None`` for world-space SOPs."""
    current = node
    while current is not None:
        world_transform = getattr(current, "worldTransform", None)
        if callable(world_transform):
            try:
                return world_transform()
            except Exception:  # noqa: BLE001
                return None
        creator = getattr(current, "creator", None)
        current = creator() if callable(creator) else None
    return None


def _world_position(hou, node, values: Iterable[float]):
    position = hou.Vector3(*[float(value) for value in values])
    transform = _object_transform(node)
    return position if transform is None else position * transform


def _ground_height(hou, ground_node, axis: int) -> float:
    geometry = ground_node.geometry()
    if geometry is None:
        raise ValueError("Ground node has no cooked geometry")
    bounds = geometry.boundingBox()
    minimum = bounds.minvec()
    maximum = bounds.maxvec()
    heights = []
    for x in (minimum[0], maximum[0]):
        for y in (minimum[1], maximum[1]):
            for z in (minimum[2], maximum[2]):
                heights.append(float(_world_position(hou, ground_node, (x, y, z))[axis]))
    return max(heights)


def validate_ground_contacts(
    rig_node: str,
    ground_node: str,
    joint_names: List[str],
    axis: str = "z",
    tolerance: float = 0.001,
    min_support_contacts: int = 3,
) -> dict:
    """Report contact clearance for named joints without mutating the scene."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not joint_names or any(not isinstance(name, str) or not name.strip() for name in joint_names):
            return skill_error("Invalid joint names", "joint_names must contain non-empty strings")
        if len(set(joint_names)) != len(joint_names):
            return skill_error("Duplicate joint names", "joint_names must be unique")
        if axis not in {"x", "y", "z"}:
            return skill_error("Invalid ground axis", axis=axis)
        if tolerance < 0:
            return skill_error("Invalid tolerance", tolerance=tolerance)
        if min_support_contacts < 1:
            return skill_error("Invalid support count", min_support_contacts=min_support_contacts)

        rig = get_node(hou, rig_node)
        ground = get_node(hou, ground_node)
        geometry = rig.geometry()
        if geometry is None:
            return skill_error("No rig geometry", rig_node=rig_node)
        name_attribute = geometry.findPointAttrib("name")
        if name_attribute is None:
            return skill_error("No name attribute", "Rig geometry has no 'name' point attribute")

        axis_index = {"x": 0, "y": 1, "z": 2}[axis]
        ground_height = _ground_height(hou, ground, axis_index)
        points = {point.attribValue(name_attribute): point for point in geometry.points()}
        contacts = []
        lifted = []
        penetrating = []
        missing = []
        samples = []
        for name in joint_names:
            point = points.get(name)
            if point is None:
                missing.append(name)
                continue
            world = _world_position(hou, rig, point.position())
            height = float(world[axis_index])
            clearance = height - ground_height
            classification = _classify(clearance, tolerance)
            samples.append(
                {
                    "joint_name": name,
                    "height": height,
                    "clearance": clearance,
                    "classification": classification,
                }
            )
            {"contact": contacts, "lifted": lifted, "penetrating": penetrating}[classification].append(name)

        passed = not missing and not penetrating and len(contacts) >= min_support_contacts
        return skill_success(
            "Validated KineFX ground contacts",
            passed=passed,
            rig_node=rig.path(),
            ground_node=ground.path(),
            axis=axis,
            ground_height=ground_height,
            tolerance=tolerance,
            required_support_contacts=min_support_contacts,
            contact_count=len(contacts),
            contacts=contacts,
            lifted=lifted,
            penetrating=penetrating,
            missing=missing,
            samples=samples,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate KineFX ground contacts")


@skill_entry
def main(**kwargs) -> dict:
    return validate_ground_contacts(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
