"""Set current frame, frame range, playback range, and FPS."""

from __future__ import annotations

from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_timeline(
    current_frame: Optional[float] = None,
    frame_range: Optional[List[float]] = None,
    playback_range: Optional[List[float]] = None,
    fps: Optional[float] = None,
) -> dict:
    """Apply timeline changes. This is the canonical timeline setter.

    Prefer this over ``houdini_automation__set_frame_range`` for interactive
    timeline edits; the automation tool remains for file-based batch flows.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        applied: dict = {}
        if fps is not None and hasattr(hou, "setFps"):
            hou.setFps(float(fps))
            applied["fps"] = float(fps)
        if frame_range is not None and len(frame_range) >= 2:
            hou.playbar.setFrameRange(float(frame_range[0]), float(frame_range[1]))
            applied["frame_range"] = [float(frame_range[0]), float(frame_range[1])]
        # Default playback range to the frame range when only the latter is given.
        pb = playback_range if playback_range is not None else frame_range
        if pb is not None and len(pb) >= 2 and hasattr(hou.playbar, "setPlaybackRange"):
            hou.playbar.setPlaybackRange(float(pb[0]), float(pb[1]))
            applied["playback_range"] = [float(pb[0]), float(pb[1])]
        if current_frame is not None and hasattr(hou, "setFrame"):
            hou.setFrame(float(current_frame))
            applied["current_frame"] = float(current_frame)
        return skill_success("Set timeline", applied=applied)
    except Exception as exc:
        return skill_exception(exc, message="Failed to set timeline")


@skill_entry
def main(**kwargs) -> dict:
    return set_timeline(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
