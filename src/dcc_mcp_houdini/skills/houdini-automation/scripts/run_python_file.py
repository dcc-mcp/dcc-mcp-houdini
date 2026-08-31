"""Run a Python file inside Houdini."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from _automation_common import existing_file, hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_OUTPUT_MODES = {"summary", "structured", "full"}
_MAX_INLINE_CHARS = 1_000_000
_SPOOL_MEMORY_BYTES = 64 * 1024


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
        return hou_import_error()

    stdout_capture: Optional[_BoundedTextCapture] = None
    stderr_capture: Optional[_BoundedTextCapture] = None
    result_capture: Optional[_BoundedTextCapture] = None
    try:
        if output_mode not in _OUTPUT_MODES:
            return skill_error(
                "Invalid output mode",
                "output_mode must be one of: full, structured, summary",
            )
        try:
            max_stdout_chars = _require_char_limit(max_stdout_chars, "max_stdout_chars")
            max_stderr_chars = _require_char_limit(max_stderr_chars, "max_stderr_chars")
            max_result_chars = _require_char_limit(max_result_chars, "max_result_chars")
        except ValueError as exc:
            return skill_error("Invalid output limit", str(exc))
        if not isinstance(spill_overflow_to_artifact, bool):
            return skill_error(
                "Invalid spill option",
                "spill_overflow_to_artifact must be a boolean",
            )

        path = existing_file(file_path, suffixes={".py"})
        if working_directory is not None and not Path(working_directory).expanduser().is_dir():
            return skill_error("Working directory not found", str(working_directory))
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
            return skill_error(
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
            )

        result_capture, inline_result, result_is_json = _capture_result(
            namespace.get("result"),
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
        return skill_success(
            "Python file executed successfully",
            **response_context,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to run Houdini Python file")
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
