"""Event-loop pump and cancel registry for foreground chunked ROP renders.

The chunked runner runs on the Houdini main thread.  Each ``step()`` call
renders one frame, and the event-loop callback schedules the next tick.
A thread-safe registry maps job ids to their ``ChunkedRunner`` + cancel
token so ``cancel_render_job`` can reach foreground jobs as well as
background (subprocess) jobs.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Callable, Dict, Optional

from dcc_mcp_core.cancellation import CancelToken
from dcc_mcp_core.chunked_runner import ChunkedOutcome, ChunkedRunner

# ---------------------------------------------------------------------------
# Thread-safe foreground job registry
# ---------------------------------------------------------------------------

_foreground_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _register_foreground_job(
    runner: ChunkedRunner,
    token: CancelToken,
    rop_path: str,
    frame_range: list,
    total: int,
) -> str:
    """Register a foreground chunked render and return its job id."""
    job_id = f"rop-fg-{uuid.uuid4().hex[:12]}"
    with _lock:
        _foreground_jobs[job_id] = {
            "runner": runner,
            "token": token,
            "rop_path": rop_path,
            "frame_range": frame_range,
            "total": total,
        }
    return job_id


def _unregister_foreground_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Remove and return the job entry, or None."""
    with _lock:
        return _foreground_jobs.pop(job_id, None)


def get_foreground_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Read the current state of a foreground chunked render job."""
    with _lock:
        job = _foreground_jobs.get(job_id)
    if job is None:
        return None

    runner: ChunkedRunner = job["runner"]
    progress = runner.progress
    outcome = runner.outcome

    result: Dict[str, Any] = {
        "job_id": job_id,
        "rop_path": job["rop_path"],
        "frame_range": job["frame_range"],
        "progress": {
            "completed": progress.completed,
            "total": progress.total,
            "last_step_at": progress.last_step_at,
        },
    }

    if outcome is not None:
        result["state"] = outcome.status
        result["completed_frames"] = progress.completed
        if outcome.status == "failed":
            result["error"] = outcome.error
    else:
        result["state"] = "running"

    return result


def cancel_foreground_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Request cancellation of a foreground chunked render; safe on repeats."""
    with _lock:
        job = _foreground_jobs.get(job_id)
    if job is None:
        return None

    runner: ChunkedRunner = job["runner"]
    runner.cancel()

    return get_foreground_job(job_id)


# ---------------------------------------------------------------------------
# Event-loop pump
# ---------------------------------------------------------------------------


def pump_runner_via_event_loop(
    runner: ChunkedRunner,
    *,
    on_terminal: Optional[Callable[[ChunkedOutcome], None]] = None,
) -> None:
    """Schedule ``runner.step()`` calls through Houdini's event loop.

    Each tick runs one bounded step.  When the runner reaches a terminal
    state the callback chain stops and ``on_terminal`` is called (if set).
    """
    import hou  # noqa: PLC0415

    def _tick() -> None:
        try:
            more = runner.step()
        except Exception:  # noqa: BLE001 - keep the pump alive on step failure
            more = False

        if more:
            hou.ui.addEventLoopCallback(_tick)
        elif on_terminal is not None and runner.outcome is not None:
            on_terminal(runner.outcome)

    hou.ui.addEventLoopCallback(_tick)
