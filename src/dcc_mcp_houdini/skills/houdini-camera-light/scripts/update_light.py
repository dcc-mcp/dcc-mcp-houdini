"""Update an existing hlight's intensity/color/exposure/type/transform."""

from __future__ import annotations

from typing import List, Optional

from _camlight_common import (  # noqa: E402
    LIGHT_TYPES,
    apply_transform,
    get_node,
    node_summary,
    set_parm_if_exists,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def update_light(
    light_path: str,
    intensity: Optional[float] = None,
    color: Optional[List[float]] = None,
    exposure: Optional[float] = None,
    light_type: Optional[str] = None,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
) -> dict:
    """Apply light changes to the hlight node at *light_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if light_type is not None and light_type.lower() not in LIGHT_TYPES:
        return skill_error(
            "Unsupported light type",
            "light_type must be one of: {}".format(", ".join(sorted(LIGHT_TYPES))),
            requested=light_type,
        )
    try:
        light = get_node(hou, light_path)
        applied = apply_transform(light, translate, rotate)
        if light_type is not None:
            set_parm_if_exists(light, "light_type", LIGHT_TYPES[light_type.lower()])
            applied["light_type"] = light_type.lower()
        if intensity is not None and set_parm_if_exists(light, "light_intensity", float(intensity)):
            applied["intensity"] = float(intensity)
        if color is not None and set_parm_if_exists(light, "light_color", color):
            applied["color"] = list(color)
        if exposure is not None and set_parm_if_exists(light, "light_exposure", float(exposure)):
            applied["exposure"] = float(exposure)
        return skill_success(
            "Updated light",
            node=node_summary(light),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to update light")


@skill_entry
def main(**kwargs) -> dict:
    return update_light(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
