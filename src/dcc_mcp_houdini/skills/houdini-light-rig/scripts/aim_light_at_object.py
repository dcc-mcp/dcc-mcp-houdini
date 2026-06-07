"""Point a light at a target object using Houdini's look-at mechanism."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _light_rig_common import (  # noqa: E402
    get_node,
    is_light_node,
    node_summary,
    set_parm_if_exists,
)


def aim_light_at_object(
    light_path: str,
    target_path: str,
    up_vector: Optional[List[float]] = None,
) -> dict:
    """Point a light at a target object using Houdini's ``lookatpath`` parameter.

    Sets the light's look-at target so it automatically orients toward the
    specified node.  Also applies an optional up-vector for finer control
    of the light's roll.

    Note:
        The ``lookatpath`` parameter is only effective for light types that
        support look-at (point, spot, area, distant, environment).  For lights
        that lack this parameter, falls back to a manual world-space aim via
        rotation calculation.

    Args:
        light_path: Path to the ``hlight`` node to aim.
        target_path: Path to the target node the light should point at.
        up_vector: Up vector [x, y, z] for the look-at constraint.
            Default ``[0, 1, 0]``.

    Returns:
        ToolResult with the light path, target path, and applied method.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        light = get_node(hou, light_path)

        if not is_light_node(light):
            return skill_error(
                "Node is not a light",
                "light_path must point to an hlight node",
                node_path=light_path,
                node_type=light.type().name(),
            )

        target = get_node(hou, target_path)
        up = list(up_vector) if up_vector else [0.0, 1.0, 0.0]

        applied = {}
        method = None

        # Primary method: use the built-in lookatpath parameter
        if set_parm_if_exists(light, "lookatpath", target.path()):
            applied["lookatpath"] = target.path()
            method = "lookatpath"
        else:
            # Fallback: manual world-space aim via vector math
            light_pos_world = light.worldTransform().extractTranslates()
            target_pos_world = target.worldTransform().extractTranslates()

            direction = hou.Vector3(target_pos_world) - hou.Vector3(light_pos_world)
            if direction.length() < 0.0001:
                return skill_error(
                    "Light and target are at the same position",
                    "Cannot aim — light and target world positions are identical.",
                    light_pos=list(light_pos_world),
                    target_pos=list(target_pos_world),
                )
            direction.normalize()

            # Build a rotation matrix from direction + up vector
            up_vec = hou.Vector3(up)
            if abs(direction.dot(up_vec)) > 0.9999:
                # Direction parallel to up — pick an alternative up
                up_vec = hou.Vector3(0, 0, 1) if abs(up_vec.y()) > 0.5 else hou.Vector3(0, 1, 0)

            side = direction.cross(up_vec)
            side.normalize()
            new_up = side.cross(direction)
            new_up.normalize()

            rot_matrix = hou.Matrix3(
                hou.Vector3(side.x(), new_up.x(), -direction.x()),
                hou.Vector3(side.y(), new_up.y(), -direction.y()),
                hou.Vector3(side.z(), new_up.z(), -direction.z()),
            )
            rot_degrees = rot_matrix.extractRotates()
            rot_list = [rot_degrees[0], rot_degrees[1], rot_degrees[2]]

            if set_parm_if_exists(light, "r", tuple(rot_list)):
                applied["rotate"] = rot_list
                method = "world_space_aim"

        if method is None:
            return skill_error(
                "Could not aim light",
                "Could not set lookatpath or compute world-space rotation.",
                light_path=light_path,
                target_path=target_path,
            )

        return skill_success(
            "Aimed light '{}' at '{}' ({})".format(light.name(), target.name(), method),
            node=node_summary(light),
            target_path=target.path(),
            method=method,
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to aim light '{}' at '{}'".format(light_path, target_path))


@skill_entry
def main(**kwargs) -> dict:
    return aim_light_at_object(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
