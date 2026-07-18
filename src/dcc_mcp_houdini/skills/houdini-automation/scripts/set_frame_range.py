"""Set Houdini frame range."""

from __future__ import annotations

from typing import Optional

from _automation_common import hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def set_frame_range(start_frame: float, end_frame: float, current_frame: Optional[float] = None) -> dict:
    """Set Houdini timeline range."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        if end_frame < start_frame:
            raise ValueError("end_frame must be greater than or equal to start_frame")
        hou.playbar.setFrameRange(start_frame, end_frame)
        hou.playbar.setPlaybackRange(start_frame, end_frame)
        if current_frame is not None:
            hou.setFrame(current_frame)
        return skill_success(
            "Updated Houdini frame range",
            start_frame=start_frame,
            end_frame=end_frame,
            current_frame=current_frame,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set Houdini frame range")


@skill_entry
def main(**kwargs) -> dict:
    return set_frame_range(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
