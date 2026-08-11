"""Durable isolated jobs for command-line Husk renders."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from _husk_common import find_hython  # noqa: E402

from dcc_mcp_houdini import _isolated_jobs

_LOG_TAIL_BYTES = 64 * 1024


def launch_husk_job(
    command: Sequence[str],
    output_path: str,
    expected_outputs: List[str],
    output_glob: str,
    environment: Mapping[str, str],
    timeout_secs: int = 3600,
) -> Dict[str, object]:
    """Launch Husk below an isolated hython worker and return immediately."""
    hython = find_hython()
    if not hython:
        raise FileNotFoundError("hython executable was not found beside Houdini")
    initial, status_path = _isolated_jobs.create_job(
        {
            "job_kind": "husk_render",
            "command": list(command),
            "output_path": output_path,
            "expected_outputs": list(expected_outputs),
            "output_glob": output_glob,
            "timeout_secs": int(timeout_secs),
        }
    )
    worker_path = Path(__file__).resolve().parent / "_husk_worker.py"
    worker_command = [
        str(hython),
        str(worker_path),
        str(status_path),
        json.dumps(list(command)),
    ]
    return _isolated_jobs.launch_job(initial["job_id"], worker_command, environment)


def _tail(path_value: object) -> str:
    if not path_value:
        return ""
    path = Path(str(path_value))
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - _LOG_TAIL_BYTES))
            payload = stream.read(_LOG_TAIL_BYTES)
    except OSError:
        return ""
    return payload.decode("utf-8", errors="replace")[-2000:]


def read_husk_job(job_id: str) -> Dict[str, object]:
    """Read one Husk job without touching Houdini's main thread."""
    result = _isolated_jobs.read_job(job_id)
    if result.get("job_kind") != "husk_render":
        raise ValueError("job_id does not identify a Husk render")
    started_at = result.get("started_at")
    if result.get("state") not in _isolated_jobs._TERMINAL_STATES and isinstance(started_at, (int, float)):
        result["elapsed_secs"] = round(max(0.0, time.time() - float(started_at)), 3)
    if result.get("state") in _isolated_jobs._TERMINAL_STATES:
        result["stdout"] = _tail(result.get("stdout_path"))
        result["stderr"] = _tail(result.get("stderr_path"))
    return result


def cancel_husk_job(job_id: str) -> Dict[str, object]:
    """Cancel an owned Husk worker tree without signalling Houdini."""
    result = read_husk_job(job_id)
    if result.get("state") in _isolated_jobs._TERMINAL_STATES:
        result["cancel_requested"] = False
        return result
    return _isolated_jobs.cancel_job(job_id)
