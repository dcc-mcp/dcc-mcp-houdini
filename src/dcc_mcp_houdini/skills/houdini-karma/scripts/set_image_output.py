"""Configure Karma image output path, format, resolution, and color space."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _karma_common import get_node, node_summary, set_first_parm, set_parm_if_exists  # noqa: E402

OUTPUT_FORMATS = {
    "exr": {"ext": ".exr", "color_depth": "half", "description": "OpenEXR (half float)"},
    "exr32": {"ext": ".exr", "color_depth": "float32", "description": "OpenEXR (full float)"},
    "png": {"ext": ".png", "color_depth": "8", "description": "PNG (8-bit)"},
    "png16": {"ext": ".png", "color_depth": "16", "description": "PNG (16-bit)"},
    "jpg": {"ext": ".jpg", "color_depth": "8", "description": "JPEG (8-bit)"},
    "tif": {"ext": ".tif", "color_depth": "16", "description": "TIFF (16-bit)"},
    "tif32": {"ext": ".tif", "color_depth": "32", "description": "TIFF (32-bit float)"},
}

COLOR_SPACES = [
    "ACES - ACEScg", "ACES - ACES2065-1", "ACES - sRGB", "Linear Rec.709",
    "sRGB", "Raw", "OCIO",
]


def set_image_output(
    node_path: str,
    output_path: str,
    format: str = "exr",
    resolution: Optional[List[int]] = None,
    color_space: Optional[str] = None,
    layer_name: Optional[str] = None,
) -> dict:
    """Set Karma image output path, format, resolution, and color space."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        applied: dict = {}
        fmt_info = OUTPUT_FORMATS.get(format.lower(), OUTPUT_FORMATS["exr"])

        # Output path
        used = set_first_parm(
            node,
            ("picture", "vm_picture", "lopoutput", "outputimage", "output_file"),
            output_path,
        )
        if used:
            applied["output_path"] = output_path
            applied["format"] = fmt_info
        else:
            applied["output_path"] = "{} (unsupported)".format(output_path)

        # Resolution
        if resolution and len(resolution) >= 2:
            w, h = int(resolution[0]), int(resolution[1])
            set_first_parm(node, ("res_overridex", "resx"), w)
            set_first_parm(node, ("res_overridey", "resy"), h)
            applied["resolution"] = [w, h]

        # Color space
        if color_space:
            used = set_first_parm(
                node,
                ("color_space", "colorspace", "vm_color_space", "vm_colorspace"),
                color_space,
            )
            applied["color_space"] = color_space if used else "unsupported"

        # Layer / product name
        if layer_name:
            set_first_parm(node, ("productname", "layer_name"), layer_name)
            applied["layer_name"] = layer_name

        return skill_success(
            "Set Karma image output",
            node=node_summary(node),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set image output")


@skill_entry
def main(**kwargs) -> dict:
    return set_image_output(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
