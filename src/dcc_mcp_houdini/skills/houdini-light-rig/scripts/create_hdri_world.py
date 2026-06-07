"""Create an environment light with an HDRI texture map for image-based lighting."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

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


def create_hdri_world(
    hdri_path: str,
    name: str = "hdri_world",
    parent_path: str = "/obj",
    intensity: float = 1.0,
    rotation: float = 0.0,
    visible_in_diffuse: bool = True,
    visible_in_specular: bool = True,
) -> dict:
    """Create an environment light (type=environment) loaded with an HDRI map.

    The environment light wraps the scene with image-based lighting from an
    ``.hdr`` or ``.exr`` file.  Configure intensity, Y-axis rotation, and
    diffuse/specular visibility.

    Args:
        hdri_path: Absolute path to the ``.hdr`` or ``.exr`` environment map.
        name: Name for the environment light node. Default ``hdri_world``.
        parent_path: Parent network. Default ``/obj``.
        intensity: Light intensity multiplier. Default 1.0.
        rotation: Y-axis rotation in degrees for the HDRI. Default 0.0.
        visible_in_diffuse: Enable diffuse contribution. Default True.
        visible_in_specular: Enable specular contribution. Default True.

    Returns:
        ToolResult with light path, HDRI path, and applied configuration.
    """
    if not hdri_path:
        return skill_error("No HDRI path provided", "hdri_path is required")

    if not os.path.exists(hdri_path):
        return skill_error(
            "HDRI file not found",
            "The specified HDRI path does not exist: {}".format(hdri_path),
            hdri_path=hdri_path,
        )

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)

        try:
            light = parent.createNode("hlight::2.0", node_name=name)
        except Exception:  # noqa: BLE001
            light = parent.createNode("hlight", node_name=name)

        applied = {}

        # Set to environment light type
        env_index = LIGHT_TYPES["environment"]
        if set_parm_if_exists(light, "light_type", env_index):
            applied["light_type"] = "environment"

        if set_parm_if_exists(light, "light_intensity", float(intensity)):
            applied["intensity"] = float(intensity)

        # Set environment map texture
        if set_parm_if_exists(light, "envmap", hdri_path):
            applied["envmap"] = hdri_path

        # Apply Y-axis rotation for HDRI orientation
        apply_transform(light, [0, 0, 0], [0, float(rotation), 0])
        applied["rotation_y"] = float(rotation)

        # Diffuse/specular contribution
        if set_parm_if_exists(light, "light_contribdiffuse", float(int(visible_in_diffuse))):
            applied["contrib_diffuse"] = visible_in_diffuse
        if set_parm_if_exists(light, "light_contribspecular", float(int(visible_in_specular))):
            applied["contrib_specular"] = visible_in_specular

        # Set the environment map color space hint (scene-linear for HDR)
        set_parm_if_exists(light, "envmap_colorSpace", "scene-linear Rec.709-sRGB")

        return skill_success(
            "Created HDRI world '{}' from '{}'".format(light.name(), hdri_path),
            node=node_summary(light),
            applied=applied,
            hdri_path=hdri_path,
            prompt="Use set_light_rig_intensity to adjust brightness or rotate the light node in Y to reorient the HDRI.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create HDRI world from '{}'".format(hdri_path))


@skill_entry
def main(**kwargs) -> dict:
    return create_hdri_world(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
