"""Durable isolated Houdini node-cook jobs."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict

from dcc_mcp_houdini import _isolated_jobs, _rop_jobs


def launch_cook_job(hou: Any, node_path: str, force: bool = False) -> Dict[str, Any]:
    """Launch a saved-scene cook in hython and return its durable job id."""
    hip_path, _ = _rop_jobs._validate_saved_hip(hou)
    executable = _rop_jobs._hython_executable()
    initial, status_path = _isolated_jobs.create_job(
        {
            "job_kind": "node_cook",
            "hip_path": str(hip_path),
            "node_path": node_path,
            "force": bool(force),
        }
    )
    worker_path = Path(__file__).resolve().parent / "_cook_worker.py"
    command = [
        str(executable),
        str(worker_path),
        str(hip_path),
        node_path,
        "1" if force else "0",
        str(status_path),
    ]
    child_env = dict(os.environ)
    child_env["DCC_MCP_BACKGROUND_COOK"] = "1"
    return _isolated_jobs.launch_job(initial["job_id"], command, child_env)


def get_cook_job(job_id: str) -> Dict[str, Any]:
    """Read and reconcile a durable cook job."""
    result = _isolated_jobs.read_job(job_id)
    if result.get("job_kind") != "node_cook":
        raise ValueError("job_id does not identify a node-cook job")
    started_at = result.get("started_at")
    if result.get("state") not in _isolated_jobs._TERMINAL_STATES and isinstance(started_at, (int, float)):
        result["elapsed_secs"] = round(max(0.0, time.time() - started_at), 3)
    return result


def cancel_cook_job(job_id: str) -> Dict[str, Any]:
    """Cancel a cook worker when this adapter process still owns it."""
    result = get_cook_job(job_id)
    if result.get("state") in _isolated_jobs._TERMINAL_STATES:
        result["cancel_requested"] = False
        return result
    return _isolated_jobs.cancel_job(job_id)
