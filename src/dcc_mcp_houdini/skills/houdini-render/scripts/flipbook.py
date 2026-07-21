"""Flipbook the current Scene Viewer over a frame range to image files.

The ``flipbook`` tool launches a chunked flipbook job that renders one
frame per host event-loop tick via the core ChunkedRunner contract. Use
``get_flipbook_job`` to poll progress and ``cancel_flipbook_job`` to
cooperatively cancel the job at the next frame boundary.

The legacy synchronous ``flipbook()`` path is preserved for backward
compatibility when called without a job-based flow, but new integrations
should use the launch/poll/cancel pattern.
"""

from __future__ import annotations

import os
from typing import List, Optional

# Chunked flipbook implementation (PIP-2790)
from _flipbook_chunked import (
    cancel_flipbook_job as _cancel_flipbook_job,
)
from _flipbook_chunked import (
    get_flipbook_job as _get_flipbook_job,
)
from _flipbook_chunked import (
    launch_flipbook_job as _launch_flipbook_job,
)
from _render_common import clamp_resolution, scene_viewer  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def flipbook(
    output_path: str,
    frame_range: List[float],
    resolution: Optional[List[int]] = None,
    camera_path: Optional[str] = None,
) -> dict:
    """Flipbook the current viewport across *frame_range* to *output_path*.

    *output_path* should contain a frame token (e.g. ``/tmp/fb.$F4.jpg``).
    UI-aware: headless sessions return ``captured: false`` with a warning.

    Returns a job descriptor with ``job_id`` for polling via
    ``get_flipbook_job`` and cancelling via ``cancel_flipbook_job``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    # Validate frame range early so invalid input is caught before launch
    if not frame_range or len(frame_range) < 2:
        return skill_error("Invalid frame range", "frame_range must be [start, end, optional increment]")

    start, end = float(frame_range[0]), float(frame_range[1])
    increment = float(frame_range[2]) if len(frame_range) >= 3 else 1.0
    if increment <= 0:
        return skill_error("Invalid frame increment", "frame_range increment must be greater than zero")
    if end < start:
        return skill_error("Invalid frame range", "frame_range end must be greater than or equal to start")

    clamped = clamp_resolution(resolution)

    try:
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

        # Ensure output directory exists
        parent = os.path.dirname(os.path.abspath(output_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

        # Launch chunked flipbook job
        result = _launch_flipbook_job(
            output_path=output_path,
            frame_range=frame_range,
            resolution=clamped,
            camera_path=camera_path,
        )

        if not result.get("success"):
            return skill_error("Flipbook launch failed", result.get("error", "Unknown error"))

        normalized_range = [start, end]
        if len(frame_range) >= 3:
            normalized_range.append(increment)

        return skill_success(
            "Flipbook job launched",
            job_id=result["job_id"],
            state=result["state"],
            captured=False,  # not yet captured — poll for completion
            output_path=output_path,
            frame_range=normalized_range,
            camera_path=camera_path,
            resolution=clamped,
            progress=result["progress"],
            warnings=result.get("warnings", []),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to launch flipbook")


def get_flipbook_job(job_id: str) -> dict:
    """Read the current state of a flipbook job.

    Returns progress, state, and terminal fields when the job has finished.
    """
    result = _get_flipbook_job(job_id)
    if not result.get("success"):
        return skill_error("Job lookup failed", result.get("error", "Unknown job"))

    state = result["state"]
    if state == "completed":
        return skill_success(
            "Flipbook complete",
            job_id=job_id,
            state="completed",
            captured=True,
            progress=result["progress"],
            written_files=result.get("written_files", []),
            skipped_frames=result.get("skipped_frames", []),
        )
    elif state == "cancelled":
        return skill_success(
            "Flipbook cancelled",
            job_id=job_id,
            state="cancelled",
            captured=True,
            progress=result["progress"],
            written_files=result.get("written_files", []),
            skipped_frames=result.get("skipped_frames", []),
        )
    elif state == "failed":
        return skill_error(
            "Flipbook failed",
            "{} ({} of {} frames completed)".format(
                result.get("error", "Unknown error"),
                result["progress"]["completed"],
                result["progress"]["total"],
            ),
        )
    else:
        # running
        return skill_success(
            "Flipbook running",
            job_id=job_id,
            state="running",
            progress=result["progress"],
        )


def cancel_flipbook_job(job_id: str) -> dict:
    """Cancel a running flipbook job. Repeated calls are safe."""
    result = _cancel_flipbook_job(job_id)
    if not result.get("success"):
        return skill_error("Cancel failed", result.get("error", "Unknown job"))

    return skill_success(
        "Flipbook cancellation requested",
        job_id=job_id,
        state=result["state"],
        progress=result["progress"],
    )


@skill_entry
def main(**kwargs) -> dict:
    return flipbook(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
