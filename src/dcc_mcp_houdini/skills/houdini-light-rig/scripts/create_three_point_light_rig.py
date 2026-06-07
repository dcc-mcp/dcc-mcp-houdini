"""Create a standard three-point key/fill/rim lighting rig."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _light_rig_common import (  # noqa: E402
    LIGHT_TYPES,
    apply_transform,
    get_node,
    node_summary,
    set_parm_if_exists,
)


def _create_rig_light(
    parent: "hou.Node",
    name: str,
    light_type: str,
    intensity: float,
    color: List[float],
    translate: List[float],
    rotate: List[float],
) -> tuple:
    """Create a single light inside a rig group and configure it."""
    try:
        light = parent.createNode("hlight::2.0", node_name=name)
    except Exception:  # noqa: BLE001
        light = parent.createNode("hlight", node_name=name)

    type_index = LIGHT_TYPES.get(light_type.lower(), 7)  # default distant
    set_parm_if_exists(light, "light_type", type_index)
    set_parm_if_exists(light, "light_intensity", float(intensity))
    set_parm_if_exists(light, "light_color", list(color))
    apply_transform(light, list(translate), list(rotate))

    return light, {
        "name": light.name(),
        "path": light.path(),
        "light_type": light_type,
        "intensity": intensity,
        "color": list(color),
        "translate": list(translate),
        "rotate": list(rotate),
    }


def create_three_point_light_rig(
    name: str = "threePoint_rig",
    parent_path: str = "/obj",
    key_intensity: float = 1.0,
    fill_intensity: float = 0.5,
    rim_intensity: float = 0.75,
    light_type: str = "distant",
    key_color: Optional[List[float]] = None,
    fill_color: Optional[List[float]] = None,
    rim_color: Optional[List[float]] = None,
    key_position: Optional[List[float]] = None,
    fill_position: Optional[List[float]] = None,
    rim_position: Optional[List[float]] = None,
) -> dict:
    """Create a standard three-point (key/fill/rim) lighting rig.

    Positions the three lights at classic three-point lighting angles:
    - Key light: 45° horizontal, -30° vertical
    - Fill light: -45° horizontal, -15° vertical
    - Rim light: behind (180°), slightly above

    Args:
        name: Base name for the rig null group and lights.
        parent_path: Parent network for the rig null node. Default ``/obj``.
        key_intensity: Key light intensity. Default 1.0.
        fill_intensity: Fill light intensity. Default 0.5.
        rim_intensity: Rim/back light intensity. Default 0.75.
        light_type: hlight type for all three lights (point, distant, spot, etc.).
        key_color: RGB for key light. Default warm white [1.0, 0.95, 0.85].
        fill_color: RGB for fill light. Default cool white [0.85, 0.90, 1.0].
        rim_color: RGB for rim light. Default neutral white [1.0, 1.0, 1.0].
        key_position: Override key light world position.
        fill_position: Override fill light world position.
        rim_position: Override rim light world position.

    Returns:
        ToolResult with rig_group, key_light, fill_light, rim_light paths.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if light_type.lower() not in LIGHT_TYPES:
        return skill_error(
            "Unsupported light type",
            "light_type must be one of: {}".format(", ".join(sorted(LIGHT_TYPES))),
            requested=light_type,
        )

    key_col = list(key_color) if key_color else [1.0, 0.95, 0.85]
    fill_col = list(fill_color) if fill_color else [0.85, 0.90, 1.0]
    rim_col = list(rim_color) if rim_color else [1.0, 1.0, 1.0]

    # Classic three-point angles (Y-up in Houdini)
    key_pos = list(key_position) if key_position else [5.0, 4.0, -5.0]  # front-right, above
    fill_pos = list(fill_position) if fill_position else [-5.0, 2.0, -5.0]  # front-left, lower
    rim_pos = list(rim_position) if rim_position else [0.0, 5.0, 8.0]  # behind, above

    key_rot = [-30.0, -45.0, 0.0]
    fill_rot = [-15.0, 45.0, 0.0]
    rim_rot = [0.0, 180.0, 0.0]

    try:
        parent = get_node(hou, parent_path)
        rig = parent.createNode("null", node_name=name)

        key_result = _create_rig_light(
            rig, "{}_key".format(name), light_type, key_intensity, key_col, key_pos, key_rot
        )
        fill_result = _create_rig_light(
            rig, "{}_fill".format(name), light_type, fill_intensity, fill_col, fill_pos, fill_rot
        )
        rim_result = _create_rig_light(
            rig, "{}_rim".format(name), light_type, rim_intensity, rim_col, rim_pos, rim_rot
        )

        return skill_success(
            "Created three-point rig '{}' ({})".format(name, light_type),
            rig_group=rig.path(),
            rig_name=rig.name(),
            key_light=key_result[1],
            fill_light=fill_result[1],
            rim_light=rim_result[1],
            light_type=light_type,
            prompt="Use aim_light_at_object to target lights, or set_light_rig_intensity to adjust overall brightness.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create three-point rig '{}'".format(name))


@skill_entry
def main(**kwargs) -> dict:
    return create_three_point_light_rig(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
