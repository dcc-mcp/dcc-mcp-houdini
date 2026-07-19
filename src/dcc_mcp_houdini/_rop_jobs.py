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
from dcc_mcp_houdini._hip_file_state import get_hip_dirty_state

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


def _validate_saved_hip(hou: Any) -> tuple:
    hip_path = Path(hou.hipFile.path())
    if not hip_path.is_file():
        raise ValueError("Background rendering requires the current HIP file to be saved")
    is_ui_available = bool(hou.isUIAvailable())
    dirty = get_hip_dirty_state(hou)
    if dirty is True:
        raise ValueError("Background rendering rejects unsaved changes; save the HIP file explicitly first")
    if is_ui_available and dirty is None:
        raise ValueError("Background rendering cannot determine the current HIP dirty state")
    return hip_path, is_ui_available


def _save_owned_hip_snapshot(hou: Any, job_dir: Path) -> Path:
    """Save a headless copy without changing or overwriting the current HIP."""
    backup_dir = hou.getenv("HOUDINI_BACKUP_DIR")
    snapshot_path = None
    hou.putenv("HOUDINI_BACKUP_DIR", str(job_dir))
    try:
        snapshot_path = Path(hou.hipFile.saveAsBackup())
    except Exception as exc:
        raise ValueError("Headless background rendering failed to create an isolated HIP snapshot") from exc
    finally:
        if backup_dir is None:
            hou.unsetenv("HOUDINI_BACKUP_DIR")
        else:
            hou.putenv("HOUDINI_BACKUP_DIR", backup_dir)
    if snapshot_path.resolve().parent != job_dir.resolve() or not snapshot_path.is_file():
        raise ValueError("Headless background rendering did not produce an owned HIP snapshot")
    return snapshot_path


def _remove_owned_hip_snapshot(status_path: Path, status: Dict[str, Any]) -> bool:
    """Remove only a snapshot located directly inside this job's directory."""
    if status.get("hip_snapshot_owned") is not True:
        return False
    snapshot_value = status.get("hip_path")
    if not snapshot_value:
        return False
    snapshot_path = Path(str(snapshot_value))
    if snapshot_path.resolve().parent != status_path.parent.resolve():
        return False
    try:
        snapshot_path.unlink()
    except FileNotFoundError:
        return False
    return True


def launch_background_render(
    hou: Any,
    rop_path: str,
    frame_range: Optional[List[float]],
    output_pattern: Optional[str],
    ignore_inputs: bool = False,
    job_kind: str = "render",
) -> Dict[str, Any]:
    """Launch one saved ROP job in an isolated hython process."""
    source_hip_path, is_ui_available = _validate_saved_hip(hou)
    executable = _hython_executable()
    initial, status_path = _isolated_jobs.create_job(
        {
            "job_kind": job_kind,
            "hip_path": str(source_hip_path),
            "rop_path": rop_path,
            "frame_range": frame_range,
            "output_pattern": output_pattern,
            "ignore_inputs": bool(ignore_inputs),
        }
    )
    hip_path = source_hip_path
    if not is_ui_available:
        try:
            hip_path = _save_owned_hip_snapshot(hou, status_path.parent)
        except Exception as exc:
            initial.update({"state": "failed", "finished_at": time.time(), "error": str(exc)})
            _isolated_jobs.write_status(status_path, initial)
            raise
        initial.update(
            {
                "hip_path": str(hip_path),
                "source_hip_path": str(source_hip_path),
                "hip_snapshot_owned": True,
            }
        )
        _isolated_jobs.write_status(status_path, initial)
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
    try:
        return _isolated_jobs.launch_job(initial["job_id"], command, child_env)
    except Exception:
        _remove_owned_hip_snapshot(status_path, initial)
        raise


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
    observed = []
    for output in expected:
        signature = _file_signature(output)
        if signature is not None and signature != before.get(output):
            observed.append(output)

    state = result.get("state")
    total = len(expected)
    if state in _isolated_jobs._TERMINAL_STATES and "written_files" in result:
        completed_outputs = list(result.get("written_files") or [])
        verification = result.get("output_verification") or {}
        worker_total = verification.get("expected_output_count")
        if isinstance(worker_total, int) and not isinstance(worker_total, bool) and worker_total >= 0:
            total = max(total, worker_total)
        total = max(total, len(completed_outputs))
    elif state == "completed":
        # Older workers did not persist written_files. A completed legacy job
        # has closed all of its observed outputs, so none remains in progress.
        completed_outputs = observed
    else:
        # Frame ranges emit expected outputs in order. The last observed file may
        # still be open, so hold it pending until the worker verifies it.
        completed_outputs = observed[:-1]

    completed = len(completed_outputs)
    result["completed"] = completed
    result["total"] = total
    result["progress"] = float(completed) / total if total else None
    if result.get("state") not in _isolated_jobs._TERMINAL_STATES or "written_files" not in result:
        result["written_files"] = completed_outputs

    started_at = result.get("started_at")
    if started_at is not None:
        finished_at = result.get("finished_at")
        elapsed = float(finished_at) - float(started_at) if finished_at is not None else time.time() - float(started_at)
        result["elapsed_secs"] = round(max(0.0, elapsed), 3)
    elapsed_secs = result.get("elapsed_secs")
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
    if result.get("state") in _isolated_jobs._TERMINAL_STATES:
        _remove_owned_hip_snapshot(_isolated_jobs._status_path(job_id), result)
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


def cancel_render_job(job_id: str, terminate: Any = None) -> Dict[str, Any]:
    result = _isolated_jobs.cancel_job(job_id, terminate=terminate)
    if result.get("state") in _isolated_jobs._TERMINAL_STATES:
        _remove_owned_hip_snapshot(_isolated_jobs._status_path(job_id), result)
    return result
