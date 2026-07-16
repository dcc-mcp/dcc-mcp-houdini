"""ROP-specific adapter for isolated Houdini jobs."""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_houdini import _isolated_jobs

_SUMMARY_WARNING_LIMIT = 10
_SUMMARY_TEXT_LIMIT = 500
_STDERR_TAIL_BYTES = 256 * 1024


def _hython_executable() -> Path:
    executable_name = "hython.exe" if os.name == "nt" else "hython"
    executable = Path(sys.executable).with_name(executable_name)
    if not executable.is_file() and os.environ.get("HFS"):
        executable = Path(os.environ["HFS"]) / "bin" / executable_name
    if not executable.is_file():
        raise FileNotFoundError("hython executable was not found beside Houdini")
    return executable


def _validate_saved_hip(hou: Any) -> Path:
    hip_path = Path(hou.hipFile.path())
    if not hip_path.is_file():
        raise ValueError("Background rendering requires the current HIP file to be saved")
    if hou.isUIAvailable():
        has_unsaved_changes = getattr(hou.hipFile, "hasUnsavedChanges", None)
        if callable(has_unsaved_changes) and has_unsaved_changes() is True:
            raise ValueError("Background rendering rejects unsaved changes; save the HIP file explicitly first")
        return hip_path

    # Houdini 21.0.631 hython may keep hasUnsavedChanges() true after save, so
    # persist the current state explicitly instead of trusting that flag or
    # launching a worker against an older disk snapshot.
    try:
        hou.hipFile.save()
    except Exception as exc:
        raise ValueError("Headless background rendering failed to save the current HIP file") from exc
    hip_path = Path(hou.hipFile.path())
    if not hip_path.is_file():
        raise ValueError("Headless background rendering did not produce a saved HIP file")
    return hip_path


def launch_background_render(
    hou: Any,
    rop_path: str,
    frame_range: Optional[List[float]],
    output_pattern: Optional[str],
    ignore_inputs: bool = False,
    job_kind: str = "render",
) -> Dict[str, Any]:
    """Launch one saved ROP job in an isolated hython process."""
    hip_path = _validate_saved_hip(hou)
    executable = _hython_executable()
    initial, status_path = _isolated_jobs.create_job(
        {
            "job_kind": job_kind,
            "hip_path": str(hip_path),
            "rop_path": rop_path,
            "frame_range": frame_range,
            "output_pattern": output_pattern,
            "ignore_inputs": bool(ignore_inputs),
        }
    )
    worker_path = Path(__file__).resolve().parent / "skills" / "houdini-render" / "scripts" / "_render_worker.py"
    command = [
        str(executable),
        str(worker_path),
        str(hip_path),
        rop_path,
        json.dumps(frame_range),
        str(status_path),
        json.dumps(output_pattern),
        json.dumps(bool(ignore_inputs)),
    ]
    child_env = dict(os.environ)
    child_env["DCC_MCP_BACKGROUND_RENDER"] = "1"
    return _isolated_jobs.launch_job(initial["job_id"], command, child_env)


def _file_signature(path: str) -> Optional[Dict[str, int]]:
    try:
        output = Path(path)
        file_stat = output.stat()
    except OSError:
        return None
    if not stat.S_ISREG(file_stat.st_mode):
        return None
    return {"mtime_ns": file_stat.st_mtime_ns, "size": file_stat.st_size}


def _with_progress(status: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(status)
    expected = list(result.get("expected_outputs") or [])
    before = dict(result.get("output_snapshot") or {})
    observed_written_files = []
    for output in expected:
        signature = _file_signature(output)
        if signature is not None and signature != before.get(output):
            observed_written_files.append(output)
    completed = len(observed_written_files)
    total = len(expected)
    result["completed"] = completed
    result["total"] = total
    result["progress"] = float(completed) / total if total else None
    if result.get("state") not in _isolated_jobs._TERMINAL_STATES or "written_files" not in result:
        result["written_files"] = observed_written_files

    started_at = result.get("started_at")
    if started_at is not None:
        finished_at = result.get("finished_at")
        elapsed = float(finished_at) - float(started_at) if finished_at is not None else time.time() - float(started_at)
        result["elapsed_secs"] = round(max(0.0, elapsed), 3)
    elapsed_secs = result.get("elapsed_secs")
    state = result.get("state")
    if state in {"failed", "cancelled", "interrupted"}:
        result["eta_secs"] = None
    elif state == "completed":
        result["eta_secs"] = 0.0 if total and completed >= total else None
    elif total and completed and elapsed_secs is not None:
        result["eta_secs"] = round(float(elapsed_secs) * (total - completed) / completed, 3)
    else:
        result["eta_secs"] = None
    return result


def _stderr_tail(status: Dict[str, Any]) -> str:
    """Read at most the bounded tail of the worker's stderr stream."""
    stderr_path = status.get("stderr_path")
    if not stderr_path:
        return ""

    try:
        with Path(str(stderr_path)).open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            offset = max(0, size - _STDERR_TAIL_BYTES)
            stream.seek(offset)
            payload = stream.read(_STDERR_TAIL_BYTES)
    except OSError:
        return ""
    if offset:
        newline = payload.find(b"\n")
        payload = payload[newline + 1 :] if newline >= 0 else b""
    return payload.decode("utf-8", errors="replace")


def _warning_lines(status: Dict[str, Any]) -> List[Any]:
    """Merge worker warnings with unique, non-empty stderr diagnostics."""
    raw_warnings = status.get("warnings", []) or []
    status_warnings = list(raw_warnings) if isinstance(raw_warnings, (list, tuple)) else [raw_warnings]
    warnings = []
    seen = set()
    for warning in status_warnings:
        normalized = " ".join(str(warning).splitlines())
        if normalized and normalized not in seen:
            seen.add(normalized)
            warnings.append(warning)
    # Houdini render diagnostics are not consistently prefixed with "Warning";
    # stderr is the worker's dedicated diagnostic stream, so retain every line.
    for raw_line in _stderr_tail(status).splitlines():
        warning = " ".join(raw_line.splitlines())
        if warning and warning not in seen:
            seen.add(warning)
            warnings.append(warning)
    return warnings


def read_render_job(job_id: str, include_details: bool = False) -> Dict[str, Any]:
    result = _with_progress(_isolated_jobs.read_job(job_id))
    warnings = _warning_lines(result)
    result["warning_count"] = len(warnings)
    if include_details:
        result["warnings"] = warnings
    if not include_details:
        result.pop("expected_outputs", None)
        result.pop("output_snapshot", None)
        written_files = list(result.pop("written_files", []) or [])
        result["written_file_count"] = len(written_files)
        result["recent_written_files"] = written_files[-10:]
        result.pop("warnings", None)
        result["recent_warnings"] = [
            " ".join(str(warning).splitlines())[:_SUMMARY_TEXT_LIMIT] for warning in warnings[-_SUMMARY_WARNING_LIMIT:]
        ]
        result.pop("traceback", None)
        error = result.pop("error", None)
        if error:
            result["error_summary"] = " ".join(str(error).splitlines())[:_SUMMARY_TEXT_LIMIT]
    return result


def cancel_render_job(job_id: str) -> Dict[str, Any]:
    return _isolated_jobs.cancel_job(job_id)
