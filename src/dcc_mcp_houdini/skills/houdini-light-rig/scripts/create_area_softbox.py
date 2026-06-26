"""Create an area light configured as a softbox for studio-style soft lighting."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _light_rig_common import (  # noqa: E402
    AREA_SHAPES,
    LIGHT_TYPES,
    apply_transform,
    get_node,
    node_summary,
    set_parm_if_exists,
)


def create_area_softbox(
    name: str = "softbox",
    parent_path: str = "/obj",
    shape: str = "grid",
    size: Optional[List[float]] = None,
    intensity: float = 2.0,
    color: Optional[List[float]] = None,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    exposure: Optional[float] = None,
) -> dict:
    """Create an area light configured as a softbox with large area and soft quality.

    Creates a ``hlight::2.0`` node with the specified shape (grid/disk/sphere/tube),
    sets a generous area size for soft shadows, and configures intensity, color,
    exposure, and transform.

    Args:
        name: Name for the area light node. Default ``softbox``.
        parent_path: Parent network. Default ``/obj``.
        shape: Area light shape (grid, disk, sphere, tube). Default ``grid``.
        size: [width, height] for grid, or [radius, radius] for disk/sphere.
            Default [5, 5] for grid, [3, 3] for others.
        intensity: Light intensity. Default 2.0 (brighter than default for softbox).
        color: RGB light color. Default neutral white [1.0, 1.0, 1.0].
        translate: World-space position [x, y, z].
        rotate: World-space rotation [rx, ry, rz] in degrees.
        exposure: Optional exposure compensation value.

    Returns:
        ToolResult with light path and applied parameters.
    """
    shape_lower = shape.lower()
    if shape_lower not in AREA_SHAPES:
        return skill_error(
            "Unsupported area shape",
            "shape must be one of: {}".format(", ".join(sorted(AREA_SHAPES))),
            requested=shape,
        )

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    # Default sizes per shape
    if size is None:
        size = [5.0, 5.0] if shape_lower == "grid" else [3.0, 3.0]

    col = list(color) if color else [1.0, 1.0, 1.0]

    try:
        parent = get_node(hou, parent_path)

        try:
            light = parent.createNode("hlight::2.0", node_name=name)
        except Exception:  # noqa: BLE001
            light = parent.createNode("hlight", node_name=name)

        applied = {}

        # Set light type
        type_index = LIGHT_TYPES.get(shape_lower, 2)
        if set_parm_if_exists(light, "light_type", type_index):
            applied["light_type"] = shape_lower

        # Intensity (softboxes are typically brighter)
        if set_parm_if_exists(light, "light_intensity", float(intensity)):
            applied["intensity"] = float(intensity)

        # Color
        if set_parm_if_exists(light, "light_color", list(col)):
            applied["color"] = list(col)

        # Area size — the key softbox parameter
        if set_parm_if_exists(light, "areasize", list(size)):
            applied["area_size"] = list(size)

        # Exposure
        if exposure is not None and set_parm_if_exists(light, "light_exposure", float(exposure)):
            applied["exposure"] = float(exposure)

        # Transform
        transform_applied = apply_transform(
            light,
            list(translate) if translate else None,
            list(rotate) if rotate else None,
        )
        applied.update(transform_applied)

        # Soft quality hints — set diffuse/specular contribution to full
        set_parm_if_exists(light, "light_contribdiffuse", 1.0)
        set_parm_if_exists(light, "light_contribspecular", 1.0)

        return skill_success(
            "Created area softbox '{}' ({} shape)".format(light.name(), shape_lower),
            node=node_summary(light),
            applied=applied,
            prompt="Use aim_light_at_object to orient the softbox toward a subject, or adjust the area_size for softer/wider illumination.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create area softbox '{}'".format(name))


@skill_entry
def main(**kwargs) -> dict:
    return create_area_softbox(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
