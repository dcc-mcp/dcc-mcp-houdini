"""Chunked flipbook runner — bounded frame-by-frame viewport capture.

Wraps the core ChunkedRunner contract so that each frame is a single
bounded step: one ``viewer.flipbook()`` call per frame with per-frame
settings. This gives the host event-loop a checkpoint between frames,
making cancellation observable, progress monotonic, and the terminal
outcome publishable exactly once.
"""

from __future__ import annotations

# Import built-in modules
import glob
import os
import time
import uuid
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence

# Import third-party modules
# (hou is imported lazily inside functions that need it)

# Import dcc_mcp_core modules
from dcc_mcp_core.cancellation import CancelledError
from dcc_mcp_core.cancellation import CancelToken

# ---------------------------------------------------------------------------
# Embedded ChunkedRunner (PIP-2788, pending next dcc-mcp-core release).
# Once the release ships this block can be replaced by:
#   from dcc_mcp_core.chunked_runner import ChunkedRunner, ChunkedStep, ChunkedProgress, ChunkedOutcome
# ---------------------------------------------------------------------------

class ChunkedStep:
    """One bounded unit of work executed on the main/affinity thread."""

    __slots__ = ("fn", "step")

    def __init__(self, step: int, fn: Callable[[], Any]) -> None:
        self.step = step
        self.fn = fn


class ChunkedProgress:
    """Monotonic progress snapshot published after each confirmed step."""

    __slots__ = ("completed", "last_step_at", "total")

    def __init__(
        self,
        completed: int = 0,
        total: int | None = None,
        last_step_at: float = 0.0,
    ) -> None:
        self.completed = completed
        self.total = total
        self.last_step_at = last_step_at


class ChunkedOutcome:
    """Terminal outcome published exactly once when the runner finishes."""

    __slots__ = ("error", "progress", "status")

    def __init__(
        self,
        status: str,
        progress: ChunkedProgress,
        error: str | None = None,
    ) -> None:
        self.status = status
        self.progress = progress
        self.error = error


class ChunkedRunner:
    """Drain a sequence of bounded work steps one tick at a time."""

    def __init__(
        self,
        steps: Sequence[ChunkedStep] | Sequence[Callable[[], Any]],
        *,
        cancel_token: CancelToken | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._steps: list[ChunkedStep] = []
        for i, item in enumerate(steps):
            if isinstance(item, ChunkedStep):
                step = item
                step.step = i
                self._steps.append(step)
            elif callable(item):
                self._steps.append(ChunkedStep(i, item))
            else:
                raise TypeError(
                    f"Expected ChunkedStep or callable, got {type(item).__name__}"
                )
        self._cancel_token = cancel_token
        self._clock = clock
        self._index: int = 0
        self._outcome: ChunkedOutcome | None = None
        self._progress = ChunkedProgress(
            completed=0,
            total=len(self._steps) if self._steps else None,
            last_step_at=0.0,
        )
        self._terminal_published: bool = False

    @property
    def progress(self) -> ChunkedProgress:
        return self._progress

    @property
    def outcome(self) -> ChunkedOutcome | None:
        return self._outcome

    @property
    def is_terminal(self) -> bool:
        return self._outcome is not None

    def step(self) -> bool:
        if self._outcome is not None:
            return False
        if self._cancel_token is not None and self._cancel_token.cancelled:
            self._publish_terminal("cancelled")
            return False
        if self._index >= len(self._steps):
            self._publish_terminal("completed")
            return False
        step = self._steps[self._index]
        try:
            step.fn()
        except CancelledError:
            self._publish_terminal("cancelled")
            return False
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            self._publish_terminal("failed", error=error_msg)
            return False
        self._index += 1
        self._progress.completed = self._index
        self._progress.last_step_at = self._clock()
        if self._index >= len(self._steps):
            self._publish_terminal("completed")
            return False
        return True

    def cancel(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.cancel()

    def _publish_terminal(self, status: str, error: str | None = None) -> None:
        if self._terminal_published:
            return
        self._outcome = ChunkedOutcome(
            status=status,
            progress=ChunkedProgress(
                completed=self._progress.completed,
                total=self._progress.total,
                last_step_at=self._progress.last_step_at,
            ),
            error=error,
        )
        self._terminal_published = True


# ---------------------------------------------------------------------------
# Flipbook job registry — shared state for launch / poll / cancel
# ---------------------------------------------------------------------------

_flipbook_jobs: Dict[str, Dict[str, Any]] = {}


def _normalize_frame_range(frame_range: List[float]) -> tuple:
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


def _expand_frame_path(output_path: str, frame: float) -> str:
    """Replace Houdini frame tokens with an exact frame number."""
    for token in ("$F4", "$F3", "$F2", "$F"):
        if token in output_path:
            # token is "$F4", "$F3", "$F2", or "$F" — extract digit part
            if len(token) > 2:
                width = int(token[2:])  # "$F4" -> 4
            else:
                width = 1  # "$F" -> default width 1
            return output_path.replace(token, f"{int(frame):0{width}d}")
    # No token — append frame number before the extension
    base, ext = os.path.splitext(output_path)
    return f"{base}.{int(frame):04d}{ext}"


def _copy_settings(source_settings, target_settings) -> None:
    """Copy flipbook settings from source to target (resolution, outputToMPlay).

    Does NOT copy frameRange or output — those are per-frame.
    """
    # Attempt to copy common settings; catch per-setting failures gracefully.
    # outputToMPlay
    try:
        target_settings.outputToMPlay(False)
    except Exception:  # noqa: BLE001
        pass

    # Resolution settings are copied from the launch-time configuration
    # (they are baked into the per-frame settings already via the caller).


def _render_single_frame(
    viewer: Any,
    viewport: Any,
    output_path: str,
    frame: float,
    resolution: Optional[List[int]] = None,
) -> Optional[str]:
    """Render one flipbook frame. Returns the written file path or None."""
    import hou  # noqa: PLC0415

    settings = viewer.flipbookSettings().stash()
    settings.frameRange((frame, frame))
    settings.output(output_path)
    try:
        settings.outputToMPlay(False)
    except Exception:  # noqa: BLE001
        pass
    if resolution is not None:
        try:
            settings.useResolution(True)
            settings.resolution(tuple(resolution))
        except Exception:  # noqa: BLE001
            pass
    viewer.flipbook(viewport, settings)
    if os.path.isfile(output_path):
        return output_path
    # Fallback: glob for the file (Houdini may add frame padding)
    dirname = os.path.dirname(os.path.abspath(output_path))
    basename = os.path.basename(output_path)
    # Replace frame number with wildcard
    import re
    pattern = re.sub(r"\d+", "*", basename)
    candidates = sorted(glob.glob(os.path.join(dirname, pattern)))
    return candidates[0] if candidates else None


def create_flipbook_chunks(
    hou: Any,
    output_path: str,
    frame_range: List[float],
    resolution: Optional[List[int]] = None,
    camera_path: Optional[str] = None,
) -> tuple:
    """Create a list of callables for ChunkedRunner, one per frame.

    Returns:
        (chunks, viewer, viewport, warnings, metadata) where:
        - chunks: list of callables for ChunkedRunner
        - viewer: the SceneViewer instance
        - viewport: the current viewport
        - warnings: list of warning strings
        - metadata: dict with frame_range, resolution, etc.
    """
    start, end, increment = _normalize_frame_range(frame_range)
    warnings: List[str] = []
    metadata: Dict[str, Any] = {
        "frame_range": [start, end, increment],
        "output_path": output_path,
    }

    if not hou.isUIAvailable():
        raise RuntimeError("UI is not available; cannot flipbook")

    viewer = None
    try:
        viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    except Exception:  # noqa: BLE001
        pass
    if viewer is None:
        raise RuntimeError("No Scene Viewer pane is open")

    viewport = viewer.curViewport()

    # Activate camera if specified
    if camera_path:
        camera = hou.node(camera_path)
        if camera is None:
            raise ValueError(f"Camera not found: {camera_path}")
        viewport.setCamera(camera)
        active = viewport.camera()
        if active is None or active.path() != camera_path:
            raise ValueError(f"Viewport did not activate camera: {camera_path}")
        metadata["camera_path"] = camera_path

    # Ensure output directory exists
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    if resolution is not None:
        metadata["resolution"] = resolution

    # Build one callable per frame
    chunks: List[Callable[[], Any]] = []
    frame = start
    tolerance = abs(increment) * 1e-9
    while frame <= end + tolerance:
        frame_output = _expand_frame_path(output_path, frame)
        # Capture by-value to avoid late-binding closure issues
        chunks.append(
            _make_frame_chunk(
                viewer=viewer,
                viewport=viewport,
                frame_output=frame_output,
                frame=frame,
                resolution=resolution,
            )
        )
        frame += increment

    return chunks, viewer, viewport, warnings, metadata


def _make_frame_chunk(
    viewer: Any,
    viewport: Any,
    frame_output: str,
    frame: float,
    resolution: Optional[List[int]],
) -> Callable[[], Optional[str]]:
    """Return a closure that renders one flipbook frame.

    Late-binding is avoided by capturing the values as default arguments.
    """
    def _chunk() -> Optional[str]:
        return _render_single_frame(
            viewer=viewer,
            viewport=viewport,
            output_path=frame_output,
            frame=frame,
            resolution=resolution,
        )

    # Store metadata for introspection in tests
    _chunk._frame = frame  # type: ignore[attr-defined]
    _chunk._frame_output = frame_output  # type: ignore[attr-defined]
    return _chunk


def _glob_outputs(output_path: str) -> list:
    """Expand frame tokens to glob and return existing files."""
    pattern = output_path
    for token in ("$F4", "$F3", "$F2", "$F"):
        pattern = pattern.replace(token, "*")
    if "*" in pattern:
        return sorted(glob.glob(pattern))
    return [output_path] if os.path.isfile(output_path) else []


def _collected_written_files(
    output_path: str,
    completed: int,
    frame_range: List[float],
) -> List[str]:
    """Return the list of written files after *completed* frames."""
    start, end, increment = _normalize_frame_range(frame_range)
    written = []
    frame = start
    count = 0
    tolerance = abs(increment) * 1e-9
    while frame <= end + tolerance and count < completed:
        frame_output = _expand_frame_path(output_path, frame)
        if os.path.isfile(frame_output):
            written.append(frame_output)
        frame += increment
        count += 1
    return written


def _skipped_frames(
    output_path: str,
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


def launch_flipbook_job(
    output_path: str,
    frame_range: List[float],
    resolution: Optional[List[int]] = None,
    camera_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Launch a chunked flipbook job. Returns a job descriptor dict.

    The returned dict contains ``job_id`` for polling via
    :func:`get_flipbook_job` and cancelling via :func:`cancel_flipbook_job`.
    """
    import hou  # noqa: PLC0415

    try:
        chunks, viewer, viewport, warnings, metadata = create_flipbook_chunks(
            hou=hou,
            output_path=output_path,
            frame_range=frame_range,
            resolution=resolution,
            camera_path=camera_path,
        )
    except (ValueError, RuntimeError) as exc:
        return {
            "success": False,
            "error": str(exc),
            "job_id": None,
        }

    token = CancelToken()
    runner = ChunkedRunner(chunks, cancel_token=token)
    job_id = f"flipbook-{uuid.uuid4().hex[:12]}"

    _flipbook_jobs[job_id] = {
        "runner": runner,
        "token": token,
        "viewer": viewer,
        "viewport": viewport,
        "output_path": output_path,
        "frame_range": metadata["frame_range"],
        "resolution": metadata.get("resolution"),
        "camera_path": metadata.get("camera_path"),
        "warnings": warnings,
        "total_frames": len(chunks),
    }

    return {
        "success": True,
        "job_id": job_id,
        "state": "running",
        "progress": {
            "completed": 0,
            "total": len(chunks),
        },
        "frame_range": metadata["frame_range"],
        "output_path": output_path,
        "resolution": metadata.get("resolution"),
        "camera_path": metadata.get("camera_path"),
        "warnings": warnings,
    }


def get_flipbook_job(job_id: str) -> Dict[str, Any]:
    """Read the current state of a flipbook job.

    Returns a dict with ``state``, ``progress``, and terminal fields
    (``written_files``, ``skipped_frames``, ``error``) when the job
    has reached a terminal state.
    """
    job = _flipbook_jobs.get(job_id)
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
            result["written_files"] = _collected_written_files(
                job["output_path"],
                progress.completed,
                job["frame_range"],
            )
            result["skipped_frames"] = []
        elif outcome.status == "cancelled":
            result["written_files"] = _collected_written_files(
                job["output_path"],
                progress.completed,
                job["frame_range"],
            )
            result["skipped_frames"] = _skipped_frames(
                job["output_path"],
                progress.completed,
                job["frame_range"],
            )
        elif outcome.status == "failed":
            result["error"] = outcome.error
    else:
        result["state"] = "running"

    return result


def cancel_flipbook_job(job_id: str) -> Dict[str, Any]:
    """Cancel a running flipbook job. Repeated calls are safe."""
    job = _flipbook_jobs.get(job_id)
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
