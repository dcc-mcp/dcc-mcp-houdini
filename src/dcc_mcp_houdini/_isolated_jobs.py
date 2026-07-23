"""Small process-owned job primitives for isolated Houdini workers."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from dcc_mcp_houdini._render_artifacts import aggregate_artifacts
from dcc_mcp_houdini._status_io import read_status as _read_status_document
from dcc_mcp_houdini._status_io import write_status

if os.name == "nt":
    from dcc_mcp_houdini._windows_process import terminate_process_tree as _terminate_windows_process_tree
else:
    _terminate_windows_process_tree = None

_JOB_ROOT_NAME = "dcc-mcp-houdini-render-jobs"
_PROCESS_HANDLES: Dict[str, Any] = {}
_PROCESS_LOCK = threading.RLock()
_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted"})
_CANCEL_GRACE_SECS = 2
_SIGTERM = getattr(signal, "SIGTERM", 15)
_SIGKILL = getattr(signal, "SIGKILL", 9)


def _status_path(job_id: str) -> Path:
    if not job_id or any(char not in "0123456789abcdef" for char in job_id.lower()):
        raise ValueError("job_id must be a hexadecimal identifier")
    return Path(tempfile.gettempdir()) / _JOB_ROOT_NAME / job_id / "status.json"


def _read_status(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError("Background job was not found")
    return _read_status_document(path)


def create_job(initial: Mapping[str, Any]) -> Tuple[Dict[str, Any], Path]:
    """Create one atomic queued status document and return it with its path."""
    job_id = uuid.uuid4().hex
    job_dir = _status_path(job_id).parent
    job_dir.mkdir(parents=True)
    status_path = job_dir / "status.json"
    status = dict(initial)
    status.update(
        {
            "job_id": job_id,
            "state": "queued",
            "stdout_path": str(job_dir / "stdout.log"),
            "stderr_path": str(job_dir / "stderr.log"),
        }
    )
    write_status(status_path, status)
    return status, status_path


def launch_job(
    job_id: str,
    command: Sequence[str],
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Launch and retain ownership of one isolated worker process."""
    status_path = _status_path(job_id)
    status = _read_status(status_path)
    stdout_path = Path(status["stdout_path"])
    stderr_path = Path(status["stderr_path"])
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(  # noqa: S603
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                cwd=str(status_path.parent),
                env=dict(env) if env is not None else None,
                creationflags=creationflags,
                close_fds=True,
                start_new_session=os.name != "nt",
            )
    except Exception as exc:
        status.update({"state": "failed", "finished_at": time.time(), "error": str(exc)})
        transaction = status.get("artifact_transaction")
        if isinstance(transaction, dict):
            transaction = dict(transaction)
            transaction["state"] = "failed"
            transaction["aggregate"] = aggregate_artifacts(transaction.get("artifacts", []))
            status["artifact_transaction"] = transaction
        write_status(status_path, status)
        raise
    result = dict(status)
    result["pid"] = process.pid
    with _PROCESS_LOCK:
        _PROCESS_HANDLES[job_id] = process
    return _with_ownership(result, True)


def _with_ownership(status: Mapping[str, Any], owned: bool) -> Dict[str, Any]:
    result = dict(status)
    result["owned_by_current_process"] = owned
    if result.get("state") in _TERMINAL_STATES:
        result["worker_liveness"] = "stopped"
    else:
        result["worker_liveness"] = "alive" if owned else "unknown"
    return result


def _finish_status(status: Dict[str, Any], state: str, return_code: int) -> Dict[str, Any]:
    finished_at = time.time()
    status.update({"state": state, "finished_at": finished_at, "return_code": return_code})
    if "started_at" in status:
        status["elapsed_secs"] = round(finished_at - float(status["started_at"]), 3)
    if state == "interrupted":
        status["error"] = "Background worker exited before reporting a terminal state"
    transaction = status.get("artifact_transaction")
    if isinstance(transaction, dict) and transaction.get("state") not in {"committed", "partially_committed"}:
        transaction = dict(transaction)
        artifacts = []
        for source in transaction.get("artifacts", []):
            artifact = dict(source)
            if artifact.get("committed") is not True:
                artifact["state"] = state
            artifacts.append(artifact)
        transaction.update(
            {
                "state": state,
                "artifacts": artifacts,
                "aggregate": aggregate_artifacts(artifacts),
            }
        )
        status["artifact_transaction"] = transaction
    return status


def _reconcile_locked(
    job_id: str,
    status_path: Path,
    status: Dict[str, Any],
    process: Any,
) -> Dict[str, Any]:
    return_code = process.poll()
    if return_code is None:
        return _with_ownership(status, True)
    if status.get("state") not in _TERMINAL_STATES:
        state = "cancelled" if status.get("state") == "cancelling" else "interrupted"
        _finish_status(status, state, return_code)
        write_status(status_path, status)
    _PROCESS_HANDLES.pop(job_id, None)
    return _with_ownership(status, False)


def _terminate_process_tree(process: Any) -> None:
    """Terminate one worker tree whose live Popen handle is owned here."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        if _terminate_windows_process_tree is None:
            raise RuntimeError("Windows process-tree termination is unavailable")
        _terminate_windows_process_tree(process, timeout_secs=_CANCEL_GRACE_SECS)
        return
    else:
        killpg = getattr(os, "killpg", None)
        if killpg is None:
            raise RuntimeError("Process-group termination is unavailable")
        try:
            killpg(process.pid, _SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=_CANCEL_GRACE_SECS)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            raise RuntimeError("Background process tree did not exit") from exc
        killpg(process.pid, _SIGKILL)
        process.wait(timeout=_CANCEL_GRACE_SECS)


def read_job(job_id: str) -> Dict[str, Any]:
    status_path = _status_path(job_id)
    with _PROCESS_LOCK:
        status = _read_status(status_path)
        process = _PROCESS_HANDLES.get(job_id)
        if process is None:
            return _with_ownership(status, False)
        return _reconcile_locked(job_id, status_path, status, process)


def cancel_job(job_id: str, terminate: Any = None) -> Dict[str, Any]:
    """Cancel a live job only when this process owns its Popen handle."""
    status_path = _status_path(job_id)
    terminate = terminate or _terminate_process_tree
    with _PROCESS_LOCK:
        status = _read_status(status_path)
        process = _PROCESS_HANDLES.get(job_id)
        if status.get("state") in _TERMINAL_STATES:
            if process is not None and process.poll() is not None:
                _PROCESS_HANDLES.pop(job_id, None)
                process = None
            result = _with_ownership(status, process is not None)
            result["cancel_requested"] = False
            return result
        if process is None:
            result = _with_ownership(status, False)
            result.update(
                {
                    "cancel_requested": False,
                    "reason": "Background job is not owned by this adapter process",
                }
            )
            return result
        if process.poll() is not None:
            result = _reconcile_locked(job_id, status_path, status, process)
            result["cancel_requested"] = False
            return result

        status.update({"state": "cancelling", "cancel_requested_at": time.time()})
        write_status(status_path, status)
        terminate(process)

        latest = _read_status(status_path)
        if latest.get("state") in _TERMINAL_STATES:
            _PROCESS_HANDLES.pop(job_id, None)
            result = _with_ownership(latest, False)
            result["cancel_requested"] = True
            return result
        return_code = process.poll()
        if return_code is None:
            raise RuntimeError("Background process tree is still running")
        _finish_status(latest, "cancelled", return_code)
        write_status(status_path, latest)
        _PROCESS_HANDLES.pop(job_id, None)
        result = _with_ownership(latest, False)
        result["cancel_requested"] = True
        return result
