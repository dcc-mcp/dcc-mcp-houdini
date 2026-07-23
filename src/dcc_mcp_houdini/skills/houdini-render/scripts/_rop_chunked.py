"""Chunked ROP runner — bounded frame-by-frame ROP render.

Wraps the core ChunkedRunner contract so that each frame is a single
bounded step: one ``rop.render()`` call per frame with per-frame
parm overrides. This gives the host event-loop a checkpoint between
frames, making cancellation observable, progress monotonic, and the
terminal outcome publishable exactly once.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from dcc_mcp_core.cancellation import CancelToken
from dcc_mcp_core.chunked_runner import ChunkedRunner

# ---------------------------------------------------------------------------
# ROP job registry — shared state for launch / poll / cancel
# ---------------------------------------------------------------------------

_rop_jobs: Dict[str, Dict[str, Any]] = {}


def _normalize_frame_range(frame_range: List[float]) -> Tuple[float, float, float]:
    """Validate and normalize a frame range, returning (start, end, increment)."""
    if not frame_range or len(frame_range) < 2:
        raise ValueError("frame_range must be [start, end, optional increment]")
    start = float(frame_range[0])
    end = float(frame_range[1])
    increment = float(frame_range[2]) if len(frame_range) >= 3 else 1.0
    if increment <= 0:
        raise ValueError("frame_range increment must be greater than zero")
    if end < start:
        raise ValueError("frame_range end must be >= start")
    return start, end, increment


def _set_single_frame_range(rop: Any, frame: float) -> None:
    """Set a ROP's frame range parms to render only *frame*."""
    # Some ROPs use `f` (tuple), others use `f1`/`f2`/`f3` scalars.
    # Setting trange=1 enables explicit frame range mode.
    try:
        rop.parm("trange").set(1)
    except Exception:  # noqa: BLE001
        pass

    f_parm = rop.parmTuple("f")
    if f_parm is not None:
        try:
            f_parm.set((frame, frame, 1.0))
            return
        except Exception:  # noqa: BLE001
            pass

    # Fallback to individual parms
    for name, value in (("f1", frame), ("f2", frame), ("f3", 1.0)):
        parm = rop.parm(name)
        if parm is not None:
            try:
                parm.set(value)
            except Exception:  # noqa: BLE001
                pass


def _eval_output_pattern(rop: Any) -> Optional[str]:
    """Evaluate the first available output parm on a ROP."""
    output_parms = ("picture", "vm_picture", "lopoutput", "sopoutput", "filename", "outputimage")
    for name in output_parms:
        parm = rop.parm(name)
        if parm is not None:
            try:
                val = parm.eval()
                if val:
                    return str(val)
            except Exception:  # noqa: BLE001
                continue
    return None


def _expand_frame_path(output_path: str, frame: float) -> str:
    """Replace Houdini frame tokens with an exact frame number."""
    for token in ("$F4", "$F3", "$F2", "$F"):
        if token in output_path:
            if len(token) > 2:
                width = int(token[2:])
            else:
                width = 1
            return output_path.replace(token, f"{int(frame):0{width}d}")
    # No token — append frame number before the extension
    base, ext = os.path.splitext(output_path)
    return f"{base}.{int(frame):04d}{ext}"


def _render_single_rop_frame(rop: Any, frame: float) -> Optional[str]:
    """Render one ROP frame. Returns an error message or None on success."""
    _set_single_frame_range(rop, frame)
    try:
        rop.render(verbose=False)
    except TypeError:
        rop.render()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _make_frame_chunk(rop: Any, frame: float) -> Callable[[], None]:
    """Return a closure that renders one ROP frame.

    Late-binding is avoided by capturing the values as default arguments.
    """

    def _chunk() -> None:
        error = _render_single_rop_frame(rop, frame)
        if error is not None:
            raise RuntimeError(f"ROP frame {frame} render failed: {error}")

    _chunk._frame = frame  # type: ignore[attr-defined]
    return _chunk


def create_rop_chunks(
    hou: Any,
    rop_path: str,
    frame_range: List[float],
) -> Tuple[List[Callable[[], Any]], Any, Dict[str, Any]]:
    """Create a list of callables for ChunkedRunner, one per ROP frame.

    Returns:
        (chunks, rop, metadata) where:
        - chunks: list of callables for ChunkedRunner
        - rop: the resolved ROP node
        - metadata: dict with frame_range, rop_path, output_pattern
    """
    start, end, increment = _normalize_frame_range(frame_range)
    rop = hou.node(rop_path)
    if rop is None:
        raise ValueError(f"ROP node not found: {rop_path}")
    if not hasattr(rop, "render"):
        raise ValueError(f"Node is not a render node: {rop_path}")

    output_pattern = _eval_output_pattern(rop)

    metadata: Dict[str, Any] = {
        "frame_range": [start, end, increment],
        "rop_path": rop_path,
        "output_pattern": output_pattern,
    }

    # Build one callable per frame
    chunks: List[Callable[[], Any]] = []
    frame = start
    tolerance = abs(increment) * 1e-9
    while frame <= end + tolerance:
        chunks.append(_make_frame_chunk(rop=rop, frame=frame))
        frame += increment

    return chunks, rop, metadata


def _collect_written_files(
    output_pattern: Optional[str],
    completed: int,
    frame_range: List[float],
) -> List[str]:
    """Return the list of written files after *completed* frames."""
    if not output_pattern:
        return []
    start, end, increment = _normalize_frame_range(frame_range)
    written = []
    frame = start
    count = 0
    tolerance = abs(increment) * 1e-9
    while frame <= end + tolerance and count < completed:
        frame_output = _expand_frame_path(output_pattern, frame)
        if os.path.isfile(frame_output):
            written.append(frame_output)
        frame += increment
        count += 1
    return written


def _collect_skipped_frames(
    output_pattern: Optional[str],
    completed: int,
    frame_range: List[float],
) -> List[float]:
    """Return the list of frame numbers that were skipped (not rendered)."""
    start, end, increment = _normalize_frame_range(frame_range)
    skipped = []
    frame = start
    count = 0
    tolerance = abs(increment) * 1e-9
    while frame <= end + tolerance:
        if count >= completed:
            skipped.append(frame)
        frame += increment
        count += 1
    return skipped


# ---------------------------------------------------------------------------
# Launch / poll / cancel
# ---------------------------------------------------------------------------


def launch_rop_job(
    rop_path: str,
    frame_range: List[float],
) -> Dict[str, Any]:
    """Launch a chunked ROP render job. Returns a job descriptor dict.

    The returned dict contains ``job_id`` for polling via
    :func:`get_rop_job` and cancelling via :func:`cancel_rop_job`.
    """
    import hou  # noqa: PLC0415

    try:
        chunks, rop, metadata = create_rop_chunks(
            hou=hou,
            rop_path=rop_path,
            frame_range=frame_range,
        )
    except (ValueError, RuntimeError) as exc:
        return {
            "success": False,
            "error": str(exc),
            "job_id": None,
        }

    token = CancelToken()
    runner = ChunkedRunner(chunks, cancel_token=token, total=len(chunks))
    job_id = f"rop-{uuid.uuid4().hex[:12]}"

    _rop_jobs[job_id] = {
        "runner": runner,
        "token": token,
        "rop_path": rop_path,
        "frame_range": metadata["frame_range"],
        "output_pattern": metadata.get("output_pattern"),
        "total_frames": len(chunks),
    }

    # Drive the runner from Houdini's event loop: each pump tick
    # executes one bounded frame step. The callback removes itself
    # when the runner reaches a terminal state.
    def _pump_callback() -> None:
        job = _rop_jobs.get(job_id)
        if job is None:
            return
        r: ChunkedRunner = job["runner"]
        if r.is_terminal:
            try:
                hou.ui.removeEventLoopCallback(_pump_callback)
            except Exception:  # noqa: BLE001
                pass
            return
        r.step()
        if r.is_terminal:
            try:
                hou.ui.removeEventLoopCallback(_pump_callback)
            except Exception:  # noqa: BLE001
                pass

    hou.ui.addEventLoopCallback(_pump_callback)

    return {
        "success": True,
        "job_id": job_id,
        "state": "running",
        "progress": {
            "completed": 0,
            "total": len(chunks),
        },
        "frame_range": metadata["frame_range"],
        "rop_path": rop_path,
        "output_pattern": metadata.get("output_pattern"),
    }


def get_rop_job(job_id: str) -> Dict[str, Any]:
    """Read the current state of a ROP render job.

    Returns a dict with ``state``, ``progress``, and terminal fields
    (``written_files``, ``skipped_frames``, ``error``) when the job
    has reached a terminal state.
    """
    job = _rop_jobs.get(job_id)
    if job is None:
        return {"success": False, "error": f"Job not found: {job_id}", "state": "unknown"}

    runner: ChunkedRunner = job["runner"]
    progress = runner.progress
    outcome = runner.outcome

    result: Dict[str, Any] = {
        "success": True,
        "job_id": job_id,
        "progress": {
            "completed": progress.completed,
            "total": progress.total,
            "last_step_at": progress.last_step_at,
        },
    }

    if outcome is not None:
        result["state"] = outcome.status
        if outcome.status == "completed":
            result["written_files"] = _collect_written_files(
                job["output_pattern"],
                progress.completed,
                job["frame_range"],
            )
            result["skipped_frames"] = []
        elif outcome.status == "cancelled":
            result["written_files"] = _collect_written_files(
                job["output_pattern"],
                progress.completed,
                job["frame_range"],
            )
            result["skipped_frames"] = _collect_skipped_frames(
                job["output_pattern"],
                progress.completed,
                job["frame_range"],
            )
        elif outcome.status == "failed":
            result["error"] = outcome.error
    else:
        result["state"] = "running"

    return result


def cancel_rop_job(job_id: str) -> Dict[str, Any]:
    """Cancel a running ROP render job. Repeated calls are safe."""
    job = _rop_jobs.get(job_id)
    if job is None:
        return {"success": False, "error": f"Job not found: {job_id}", "state": "unknown"}

    runner: ChunkedRunner = job["runner"]
    runner.cancel()

    progress = runner.progress
    return {
        "success": True,
        "job_id": job_id,
        "state": "cancelling",
        "progress": {
            "completed": progress.completed,
            "total": progress.total,
        },
    }
