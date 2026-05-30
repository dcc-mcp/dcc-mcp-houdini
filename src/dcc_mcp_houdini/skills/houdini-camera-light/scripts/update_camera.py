"""Update an existing camera's transform, resolution, and focal length."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _camlight_common import apply_transform, get_node, node_summary, set_parm_if_exists  # noqa: E402


def update_camera(
    camera_path: str,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    resolution: Optional[List[int]] = None,
    focal: Optional[float] = None,
) -> dict:
    """Apply lens/transform changes to the camera at *camera_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        cam = get_node(hou, camera_path)
        applied = apply_transform(cam, translate, rotate)
        if resolution is not None and len(resolution) >= 2:
            set_parm_if_exists(cam, "resx", int(resolution[0]))
            set_parm_if_exists(cam, "resy", int(resolution[1]))
            applied["resolution"] = [int(resolution[0]), int(resolution[1])]
        if focal is not None and set_parm_if_exists(cam, "focal", float(focal)):
            applied["focal"] = float(focal)
        return skill_success(
            "Updated camera",
            node=node_summary(cam),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to update camera")


@skill_entry
def main(**kwargs) -> dict:
    return update_camera(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
