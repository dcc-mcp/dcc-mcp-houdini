"""Set renderer camera/resolution/frame-range/output/format on a ROP node."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import (  # noqa: E402
    apply_frame_range,
    clamp_resolution,
    get_node,
    node_summary,
    set_first_parm,
)


def set_render_settings(
    rop_path: str,
    camera: Optional[str] = None,
    resolution: Optional[List[int]] = None,
    frame_range: Optional[List[float]] = None,
    output_path: Optional[str] = None,
    image_format: Optional[str] = None,
) -> dict:
    """Apply render settings to the ROP at *rop_path* (defensive parm writes)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rop = get_node(hou, rop_path)
        applied: dict = {}
        unsupported: List[str] = []
        if camera is not None:
            if set_first_parm(rop, ("camera", "render_camera"), camera):
                applied["camera"] = camera
            else:
                unsupported.append("camera")
        clamped = clamp_resolution(resolution)
        if clamped is not None:
            x = set_first_parm(rop, ("res_overridex", "resx", "vm_resx"), clamped[0])
            y = set_first_parm(rop, ("res_overridey", "resy", "vm_resy"), clamped[1])
            if x or y:
                applied["resolution"] = clamped
            else:
                unsupported.append("resolution")
        if frame_range is not None:
            applied["frame_range"] = apply_frame_range(rop, frame_range)
        if output_path is not None:
            used = set_first_parm(
                rop,
                ("picture", "vm_picture", "lopoutput", "sopoutput", "filename", "outputimage"),
                output_path,
            )
            if used:
                applied["output_path"] = output_path
            else:
                unsupported.append("output_path")
        if image_format is not None:
            used = set_first_parm(rop, ("vm_image_format", "image_format"), image_format)
            if used:
                applied["image_format"] = image_format
            else:
                unsupported.append("image_format")
        return skill_success(
            "Set render settings",
            rop=node_summary(rop),
            applied=applied,
            unsupported=unsupported,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set render settings")


@skill_entry
def main(**kwargs) -> dict:
    return set_render_settings(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
