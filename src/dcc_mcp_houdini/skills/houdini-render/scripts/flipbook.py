"""Flipbook the current Scene Viewer over a frame range to image files."""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import clamp_resolution, scene_viewer  # noqa: E402


def _glob_outputs(output_path: str) -> list:
    # Expand a $F / $F4 style pattern to a filesystem glob for verification.
    pattern = output_path
    for token in ("$F4", "$F3", "$F2", "$F"):
        pattern = pattern.replace(token, "*")
    if "*" in pattern:
        return sorted(glob.glob(pattern))
    return [output_path] if os.path.isfile(output_path) else []


def flipbook(
    output_path: str,
    frame_range: List[float],
    resolution: Optional[List[int]] = None,
) -> dict:
    """Flipbook the current viewport across *frame_range* to *output_path*.

    *output_path* should contain a frame token (e.g. ``/tmp/fb.$F4.jpg``).
    UI-aware: headless sessions return ``captured: false`` with a warning.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if not frame_range or len(frame_range) < 2:
        return skill_error("Invalid frame range", "frame_range must be [start, end]")

    try:
        clamped = clamp_resolution(resolution)
        if not hou.isUIAvailable():
            return skill_success(
                "Flipbook unavailable (headless)",
                captured=False,
                output_path=output_path,
                written_files=[],
                skipped=[output_path],
                warnings=["UI is not available; cannot flipbook"],
            )
        viewer = scene_viewer(hou)
        if viewer is None:
            return skill_success(
                "No Scene Viewer pane",
                captured=False,
                output_path=output_path,
                written_files=[],
                skipped=[output_path],
                warnings=["No Scene Viewer pane is open"],
            )
        start, end = float(frame_range[0]), float(frame_range[1])
        parent = os.path.dirname(os.path.abspath(output_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        warnings: List[str] = []
        settings = viewer.flipbookSettings().stash()
        settings.frameRange((start, end))
        settings.output(output_path)
        try:
            settings.outputToMPlay(False)
        except Exception:  # noqa: BLE001
            pass
        if clamped is not None:
            try:
                settings.useResolution(True)
                settings.resolution(tuple(clamped))
            except Exception as res_exc:  # noqa: BLE001
                warnings.append("Could not set resolution: {}".format(res_exc))
        viewer.flipbook(viewer.curViewport(), settings)
        written = _glob_outputs(output_path)
        return skill_success(
            "Flipbook complete",
            captured=bool(written),
            output_path=output_path,
            frame_range=[start, end],
            resolution=clamped,
            written_files=written,
            skipped=[] if written else [output_path],
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to flipbook viewport")


@skill_entry
def main(**kwargs) -> dict:
    return flipbook(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
