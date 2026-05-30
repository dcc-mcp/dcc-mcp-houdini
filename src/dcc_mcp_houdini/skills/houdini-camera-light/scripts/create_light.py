"""Create an hlight node with typed intensity/color/exposure/transform."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _camlight_common import (  # noqa: E402
    LIGHT_TYPES,
    apply_transform,
    get_node,
    node_summary,
    set_parm_if_exists,
)


def create_light(
    parent_path: str = "/obj",
    light_type: str = "point",
    name: Optional[str] = None,
    intensity: Optional[float] = None,
    color: Optional[List[float]] = None,
    exposure: Optional[float] = None,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
) -> dict:
    """Create an ``hlight::2.0`` node and configure its core light parms."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    type_index = LIGHT_TYPES.get(light_type.lower())
    if type_index is None:
        return skill_error(
            "Unsupported light type",
            "light_type must be one of: {}".format(", ".join(sorted(LIGHT_TYPES))),
            requested=light_type,
        )
    try:
        parent = get_node(hou, parent_path)
        try:
            light = parent.createNode("hlight::2.0", node_name=name)
        except Exception:  # noqa: BLE001 - older Houdini uses unversioned hlight
            light = parent.createNode("hlight", node_name=name)
        applied = apply_transform(light, translate, rotate)
        set_parm_if_exists(light, "light_type", type_index)
        applied["light_type"] = light_type.lower()
        if intensity is not None and set_parm_if_exists(light, "light_intensity", float(intensity)):
            applied["intensity"] = float(intensity)
        if color is not None and set_parm_if_exists(light, "light_color", color):
            applied["color"] = list(color)
        if exposure is not None and set_parm_if_exists(light, "light_exposure", float(exposure)):
            applied["exposure"] = float(exposure)
        return skill_success(
            "Created light",
            parent_path=parent.path(),
            node=node_summary(light),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create light")


@skill_entry
def main(**kwargs) -> dict:
    return create_light(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
