"""Capture the current Scene Viewer to an image file (flipbook, single frame)."""

from __future__ import annotations

import os
from typing import List, Optional

from _render_common import clamp_resolution, scene_viewer  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def capture_viewport(
    output_path: str,
    resolution: Optional[List[int]] = None,
    frame: Optional[float] = None,
) -> dict:
    """Flipbook the current viewport to *output_path* for a single frame.

    UI-aware: a headless ``hython`` session returns ``captured: false`` with a
    structured warning rather than failing.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        clamped = clamp_resolution(resolution)
        if not hou.isUIAvailable():
            return skill_success(
                "Viewport capture unavailable (headless)",
                captured=False,
                output_path=output_path,
                written_files=[],
                skipped=[output_path],
                warnings=["UI is not available; cannot capture a viewport"],
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
        target_frame = float(frame) if frame is not None else float(hou.frame())
        parent = os.path.dirname(os.path.abspath(output_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        warnings: List[str] = []
        settings = viewer.flipbookSettings().stash()
        settings.frameRange((target_frame, target_frame))
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
        written = [output_path] if os.path.isfile(output_path) else []
        skipped = [] if written else [output_path]
        return skill_success(
            "Captured viewport",
            captured=bool(written),
            output_path=output_path,
            frame=target_frame,
            resolution=clamped,
            written_files=written,
            skipped=skipped,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to capture viewport")


@skill_entry
def main(**kwargs) -> dict:
    return capture_viewport(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
