"""Query current frame, frame/playback range, FPS, and time units."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_timeline() -> dict:
    """Return the canonical timeline state for the current hip."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        playbar = hou.playbar
        frame_range = list(playbar.frameRange()) if hasattr(playbar, "frameRange") else None
        playback_range = list(playbar.playbackRange()) if hasattr(playbar, "playbackRange") else None
        fps = hou.fps() if hasattr(hou, "fps") else None
        return skill_success(
            "Read timeline",
            current_frame=hou.frame() if hasattr(hou, "frame") else None,
            current_time=hou.time() if hasattr(hou, "time") else None,
            frame_range=[float(frame_range[0]), float(frame_range[1])] if frame_range else None,
            playback_range=[float(playback_range[0]), float(playback_range[1])] if playback_range else None,
            fps=fps,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read timeline")


@skill_entry
def main(**kwargs) -> dict:
    return get_timeline(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
