"""Run a Python file inside Houdini."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, Optional

from _automation_common import existing_file, hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_OUTPUT_MODES = {"summary", "structured", "full"}
_MAX_INLINE_CHARS = 1_000_000
_SPOOL_MEMORY_BYTES = 64 * 1024

# Terminal states for ``context.execution_state``. They describe the host-side
# execution of the Python file, not the transport result and not the script's
# own reported outcome.
_STATE_NOT_STARTED = "not_started"
_STATE_EXCEPTION = "exception"
_STATE_COMPLETED = "completed"
# The script body finished, but capturing/serializing its result or persisting
# an overflow artifact failed. The script may already have mutated the scene, so
# this is never reported as a completed success.
_STATE_POST_PROCESSING_FAILED = "post_processing_failed"

# States where the script ran far enough to produce a ``result`` verdict, so
# ``script_result_success`` is meaningful and must be preserved on the envelope.
_VERDICT_STATES = frozenset({_STATE_COMPLETED, _STATE_POST_PROCESSING_FAILED})

# Consumer guidance attached to a completed run. Finding 1 (issue #364): an
# unattended agent that receives a client-side timeout must not assume the job
# was cancelled or dead and blindly retry a destructive/long-running script.
_STATUS_PROMPT = (
    "Top-level success reports that the Python file finished executing on the "
    "host (see execution_state); it does NOT certify the script's own work. "
    "When the script sets `result` to a mapping with a boolean 'success' key, "
    "that verdict is surfaced separately as script_result_success "
    "(true/false, or null when no valid verdict). Distinguish a completed job from a nested "
    "result.success=false before deciding to retry. This tool is synchronous "
    "and main-thread bound with no async job handle or cancel path: a "
    "client-side timeout is NOT a cancellation and the host may still be "
    "running the script. Do not blindly retry a destructive or long-running "
    "script on timeout; poll a side-effect status/result file for the terminal "
    "state instead."
)


def _script_result_success(value: Any) -> Optional[bool]:
    """Return the executed script's own boolean verdict, if it reported one.

    Many Houdini automation scripts set ``result = {"success": bool, ...}``.
    Only a strict boolean ``success`` member of a mapping counts as a verdict;
    anything else (None, a string/number, a non-mapping, or a non-boolean
    ``success``) is reported as ``None``, meaning "the script did not report a
    verdict". This keeps the job/transport success separate from the script's
    own outcome so a nested ``result.success=false`` is never mistaken for a
    completed-and-successful job.
    """
    try:
        if isinstance(value, Mapping) and isinstance(value.get("success"), bool):
            return value["success"]
    except Exception:
        # A pathological result object must never break envelope construction,
        # especially while reporting a post-processing failure.
        return None
    return None


def _with_status(result: dict, execution_state: str, raw_result: Any = None) -> dict:
    """Attach explicit execution/result status semantics to a result envelope.

    The script's own verdict is surfaced for any state where the body ran far
    enough to set ``result`` (including a post-processing failure), so it is
    never silently dropped by a later serialization error. The completed-run
    guidance is attached only to a genuinely completed, successfully captured
    run — a mislabeled ``success=False`` envelope must never carry it.
    """
    context = result.setdefault("context", {})
    context["execution_state"] = execution_state
    context["script_result_success"] = (
        _script_result_success(raw_result) if execution_state in _VERDICT_STATES else None
    )
    if execution_state == _STATE_COMPLETED and result.get("success") is True:
        result["prompt"] = _STATUS_PROMPT
    return result


class _BoundedTextCapture:
    """Capture text with bounded memory and an optional durable overflow copy."""

    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars
        self.total_chars = 0
        self._stream = tempfile.SpooledTemporaryFile(
            max_size=_SPOOL_MEMORY_BYTES,
            mode="w+t",
            encoding="utf-8",
            newline="",
        )

    @property
    def truncated(self) -> bool:
        return self.total_chars > self.max_chars

    def write(self, value: str) -> int:
        text = str(value)
        self.total_chars += len(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()

    def reset(self) -> None:
        self._stream.seek(0)
        self._stream.truncate(0)
        self.total_chars = 0

    def preview(self) -> str:
        self._stream.flush()
        position = self._stream.tell()
        try:
            self._stream.seek(0)
            return self._stream.read(self.max_chars)
        finally:
            self._stream.seek(position)

    def persist(self, label: str, force: bool = False, suffix: str = ".txt") -> Optional[dict]:
        if self.total_chars == 0 or (not force and not self.truncated):
            return None

        self._stream.flush()
        position = self._stream.tell()
        artifact_path: Optional[Path] = None
        digest = hashlib.sha256()
        byte_count = 0
        try:
            self._stream.seek(0)
            with tempfile.NamedTemporaryFile(
                prefix="dcc-mcp-houdini-{}-".format(label),
                suffix=suffix,
                delete=False,
            ) as artifact:
                artifact_path = Path(artifact.name).resolve()
                while True:
                    chunk = self._stream.read(64 * 1024)
                    if not chunk:
                        break
                    encoded = chunk.encode("utf-8")
                    artifact.write(encoded)
                    digest.update(encoded)
                    byte_count += len(encoded)
        except Exception:
            if artifact_path is not None:
                try:
                    artifact_path.unlink()
                except FileNotFoundError:
                    pass
            raise
        finally:
            self._stream.seek(position)

        return {
            "path": str(artifact_path),
            "chars": self.total_chars,
            "bytes": byte_count,
            "sha256": digest.hexdigest(),
            "encoding": "utf-8",
        }

    def close(self) -> None:
        self._stream.close()


def _require_char_limit(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_INLINE_CHARS:
        raise ValueError("{} must be an integer from 0 to {}".format(label, _MAX_INLINE_CHARS))
    return value


def _capture_result(value: Any, max_chars: int, output_mode: str) -> tuple:
    capture = _BoundedTextCapture(max_chars)
    if value is None:
        return capture, None, False

    if output_mode == "full":
        capture.write(str(value))
        return capture, capture.preview(), False

    json_encoded = True
    try:
        encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        for chunk in encoder.iterencode(value):
            capture.write(chunk)
    except (TypeError, ValueError):
        json_encoded = False
        capture.reset()
        capture.write(str(value))

    if output_mode == "summary" or capture.truncated:
        return capture, None, json_encoded
    if json_encoded:
        return capture, json.loads(capture.preview()), True
    return capture, capture.preview(), False


def _output_summary(
    output_mode: str,
    stdout_capture: _BoundedTextCapture,
    stderr_capture: _BoundedTextCapture,
    result_capture: _BoundedTextCapture,
    result_is_json: bool,
    spill_overflow_to_artifact: bool,
) -> dict:
    captures = {
        "stdout": stdout_capture,
        "stderr": stderr_capture,
        "result": result_capture,
    }
    artifacts: Dict[str, dict] = {}
    if spill_overflow_to_artifact:
        force = output_mode == "summary"
        try:
            for label, capture in captures.items():
                artifact = capture.persist(
                    label,
                    force=force,
                    suffix=".json" if label == "result" and result_is_json else ".txt",
                )
                if artifact is not None:
                    artifacts[label] = artifact
        except Exception:
            for artifact in artifacts.values():
                try:
                    Path(artifact["path"]).unlink()
                except FileNotFoundError:
                    pass
            raise
    return {
        "mode": output_mode,
        "stdout_chars": stdout_capture.total_chars,
        "stderr_chars": stderr_capture.total_chars,
        "result_chars": result_capture.total_chars,
        "truncated": {label: capture.truncated for label, capture in captures.items()},
        "artifacts": artifacts,
    }


@contextlib.contextmanager
def _pushd(path: Optional[str]):
    if not path:
        yield
        return
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run_python_file(
    file_path: str,
    args: Optional[List[Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    working_directory: Optional[str] = None,
    output_mode: str = "full",
    max_stdout_chars: int = 4000,
    max_stderr_chars: int = 4000,
    max_result_chars: int = 8000,
    spill_overflow_to_artifact: bool = True,
) -> dict:
    """Execute a Python file with Houdini globals and bounded inline output."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return _with_status(hou_import_error(), _STATE_NOT_STARTED)

    stdout_capture: Optional[_BoundedTextCapture] = None
    stderr_capture: Optional[_BoundedTextCapture] = None
    result_capture: Optional[_BoundedTextCapture] = None
    raw_result: Any = None
    # Tracks how far host-side execution got, so an unexpected internal error
    # is still reported with a meaningful terminal state instead of a bare
    # generic INTERNAL_ERROR-style failure.
    execution_state = _STATE_NOT_STARTED
    try:
        if output_mode not in _OUTPUT_MODES:
            return _with_status(
                skill_error(
                    "Invalid output mode",
                    "output_mode must be one of: full, structured, summary",
                ),
                _STATE_NOT_STARTED,
            )
        try:
            max_stdout_chars = _require_char_limit(max_stdout_chars, "max_stdout_chars")
            max_stderr_chars = _require_char_limit(max_stderr_chars, "max_stderr_chars")
            max_result_chars = _require_char_limit(max_result_chars, "max_result_chars")
        except ValueError as exc:
            return _with_status(skill_error("Invalid output limit", str(exc)), _STATE_NOT_STARTED)
        if not isinstance(spill_overflow_to_artifact, bool):
            return _with_status(
                skill_error(
                    "Invalid spill option",
                    "spill_overflow_to_artifact must be a boolean",
                ),
                _STATE_NOT_STARTED,
            )

        path = existing_file(file_path, suffixes={".py"})
        if working_directory is not None and not Path(working_directory).expanduser().is_dir():
            return _with_status(
                skill_error("Working directory not found", str(working_directory)),
                _STATE_NOT_STARTED,
            )
        namespace: Dict[str, Any] = {
            "__file__": str(path),
            "__name__": "__dcc_mcp_houdini_script__",
            "hou": hou,
            "args": list(args or []),
            "context": dict(context or {}),
        }
        namespace.update(context or {})
        stdout_capture = _BoundedTextCapture(max_stdout_chars)
        stderr_capture = _BoundedTextCapture(max_stderr_chars)
        execution_state = _STATE_EXCEPTION
        try:
            with _pushd(working_directory), contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(
                stderr_capture
            ):
                exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
        except Exception:
            error = traceback.format_exc()
            stderr_capture.write(error)
            result_capture = _BoundedTextCapture(max_result_chars)
            output_summary = _output_summary(
                output_mode,
                stdout_capture,
                stderr_capture,
                result_capture,
                result_is_json=False,
                spill_overflow_to_artifact=spill_overflow_to_artifact,
            )
            return _with_status(
                skill_error(
                    "Python file execution failed",
                    (
                        "See output_summary artifacts for the captured traceback"
                        if output_mode == "summary"
                        else stderr_capture.preview()
                    ),
                    stdout=None if output_mode == "summary" else stdout_capture.preview(),
                    stderr=None if output_mode == "summary" else stderr_capture.preview(),
                    result=None,
                    output_summary=output_summary,
                ),
                _STATE_EXCEPTION,
            )

        raw_result = namespace.get("result")
        # The script body has finished, but capturing/serializing its result and
        # persisting artifacts can still fail. Until the final success envelope is
        # built, any exception is a post-processing failure, not a completed job.
        # This blocks a success=False error envelope from being labeled completed.
        execution_state = _STATE_POST_PROCESSING_FAILED
        result_capture, inline_result, result_is_json = _capture_result(
            raw_result,
            max_result_chars,
            output_mode,
        )
        output_summary = _output_summary(
            output_mode,
            stdout_capture,
            stderr_capture,
            result_capture,
            result_is_json=result_is_json,
            spill_overflow_to_artifact=spill_overflow_to_artifact,
        )
        response_context = {
            "file_path": str(path),
            "stdout": None if output_mode == "summary" else stdout_capture.preview(),
            "stderr": None if output_mode == "summary" else stderr_capture.preview(),
            "result": inline_result,
            "output_summary": output_summary,
        }
        if output_mode == "structured" and result_capture.truncated:
            response_context["result_preview"] = result_capture.preview()
        return _with_status(
            skill_success(
                "Python file executed successfully",
                **response_context,
            ),
            _STATE_COMPLETED,
            raw_result,
        )
    except Exception as exc:
        return _with_status(
            skill_exception(exc, message="Failed to run Houdini Python file"),
            execution_state,
            raw_result,
        )
    finally:
        if stdout_capture is not None:
            stdout_capture.close()
        if stderr_capture is not None:
            stderr_capture.close()
        if result_capture is not None:
            result_capture.close()


@skill_entry
def main(**kwargs) -> dict:
    return run_python_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
