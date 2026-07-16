"""Launch and inspect isolated hython render jobs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

_PROCESS_HANDLES: dict[str, Any] = {}
_PROCESS_LOCK = threading.RLock()
_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted"})
_CANCEL_GRACE_SECS = 2
_SIGTERM = getattr(signal, "SIGTERM", 15)
_SIGKILL = getattr(signal, "SIGKILL", 9)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    pending = path.with_name("{}.{}.tmp".format(path.name, os.getpid()))
    pending.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(str(pending), str(path))


def _status_path(job_id: str) -> Path:
    if not job_id or any(char not in "0123456789abcdef" for char in job_id.lower()):
        raise ValueError("job_id must be a hexadecimal identifier")
    return Path(tempfile.gettempdir()) / "dcc-mcp-houdini-render-jobs" / job_id / "status.json"


def _read_status(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError("Render job was not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _with_ownership(status: dict[str, Any], owned: bool) -> dict[str, Any]:
    result = dict(status)
    result["owned_by_current_process"] = owned
    return result


def _finish_status(status: dict[str, Any], state: str, return_code: int) -> dict[str, Any]:
    finished_at = time.time()
    status.update({"state": state, "finished_at": finished_at, "return_code": return_code})
    if "started_at" in status:
        status["elapsed_secs"] = round(finished_at - float(status["started_at"]), 3)
    if state == "interrupted":
        status["error"] = "Background render worker exited before reporting a terminal state"
    return status


def _reconcile_locked(
    job_id: str,
    status_path: Path,
    status: dict[str, Any],
    process: Any,
) -> dict[str, Any]:
    return_code = process.poll()
    if return_code is None:
        return _with_ownership(status, True)
    if status.get("state") not in _TERMINAL_STATES:
        state = "cancelled" if status.get("state") == "cancelling" else "interrupted"
        _finish_status(status, state, return_code)
        _write_json(status_path, status)
    _PROCESS_HANDLES.pop(job_id, None)
    return _with_ownership(status, False)


def _terminate_process_tree(process: Any) -> None:
    """Terminate one worker tree whose live Popen handle is owned here."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        completed = subprocess.run(  # noqa: S603
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode and process.poll() is None:
            raise RuntimeError("Failed to terminate the background render process tree")
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
            raise RuntimeError("Background render process tree did not exit") from exc
        killpg(process.pid, _SIGKILL)
        process.wait(timeout=_CANCEL_GRACE_SECS)


def launch_background_render(
    hou: Any,
    rop_path: str,
    frame_range: Optional[list[float]],
    output_pattern: Optional[str],
) -> dict[str, Any]:
    hip_path = Path(hou.hipFile.path())
    if not hip_path.is_file():
        raise ValueError("Background rendering requires the current HIP file to be saved")

    job_id = uuid.uuid4().hex
    job_dir = Path(tempfile.gettempdir()) / "dcc-mcp-houdini-render-jobs" / job_id
    job_dir.mkdir(parents=True)
    status_path = job_dir / "status.json"
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"
    worker_path = Path(__file__).with_name("_render_worker.py")
    executable_name = "hython.exe" if os.name == "nt" else "hython"
    executable = Path(sys.executable).with_name(executable_name)
    if not executable.is_file() and os.environ.get("HFS"):
        executable = Path(os.environ["HFS"]) / "bin" / executable_name
    if not executable.is_file():
        raise FileNotFoundError("hython executable was not found beside Houdini")
    command = [
        str(executable),
        str(worker_path),
        str(hip_path),
        rop_path,
        json.dumps(frame_range),
        str(status_path),
        json.dumps(output_pattern),
    ]
    initial = {
        "job_id": job_id,
        "state": "queued",
        "hip_path": str(hip_path),
        "rop_path": rop_path,
        "frame_range": frame_range,
        "output_pattern": output_pattern,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    _write_json(status_path, initial)
    child_env = dict(os.environ)
    child_env["DCC_MCP_BACKGROUND_RENDER"] = "1"
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            cwd=str(job_dir),
            env=child_env,
            creationflags=creationflags,
            close_fds=True,
            start_new_session=os.name != "nt",
        )
    initial.update({"pid": process.pid})
    with _PROCESS_LOCK:
        _PROCESS_HANDLES[job_id] = process
    return initial


def read_render_job(job_id: str) -> dict[str, Any]:
    status_path = _status_path(job_id)
    with _PROCESS_LOCK:
        status = _read_status(status_path)
        process = _PROCESS_HANDLES.get(job_id)
        if process is None:
            return _with_ownership(status, False)
        return _reconcile_locked(job_id, status_path, status, process)


def cancel_render_job(job_id: str) -> dict[str, Any]:
    """Cancel a live render only when this process owns its Popen handle."""
    status_path = _status_path(job_id)
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
                    "reason": "Render job is not owned by this adapter process",
                }
            )
            return result
        if process.poll() is not None:
            result = _reconcile_locked(job_id, status_path, status, process)
            result["cancel_requested"] = False
            return result

        status.update({"state": "cancelling", "cancel_requested_at": time.time()})
        _write_json(status_path, status)
        _terminate_process_tree(process)

        latest = _read_status(status_path)
        if latest.get("state") in _TERMINAL_STATES:
            result = _with_ownership(latest, process.poll() is None)
            result["cancel_requested"] = True
            return result
        return_code = process.poll()
        if return_code is None:
            raise RuntimeError("Background render process tree is still running")
        _finish_status(latest, "cancelled", return_code)
        _write_json(status_path, latest)
        _PROCESS_HANDLES.pop(job_id, None)
        result = _with_ownership(latest, False)
        result["cancel_requested"] = True
        return result
