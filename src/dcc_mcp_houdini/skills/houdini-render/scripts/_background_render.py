"""Compatibility adapter for package-owned isolated ROP jobs."""

from __future__ import annotations

from dcc_mcp_houdini import _isolated_jobs, _rop_jobs

os = _isolated_jobs.os
subprocess = _isolated_jobs.subprocess
sys = _rop_jobs.sys
tempfile = _isolated_jobs.tempfile
time = _isolated_jobs.time
launch_background_render = _rop_jobs.launch_background_render
read_render_job = _rop_jobs.read_render_job
_PROCESS_HANDLES = _isolated_jobs._PROCESS_HANDLES
_PROCESS_LOCK = _isolated_jobs._PROCESS_LOCK
_TERMINAL_STATES = _isolated_jobs._TERMINAL_STATES
_SIGTERM = _isolated_jobs._SIGTERM
_SIGKILL = _isolated_jobs._SIGKILL
_terminate_process_tree = _isolated_jobs._terminate_process_tree


def cancel_render_job(job_id: str) -> dict:
    return _isolated_jobs.cancel_job(job_id, terminate=_terminate_process_tree)
