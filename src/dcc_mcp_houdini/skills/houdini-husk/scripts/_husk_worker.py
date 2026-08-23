"""Isolated hython worker that owns one blocking Husk process."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

from dcc_mcp_houdini._status_io import read_status, write_status

_STDERR_SCAN_BYTES = 64 * 1024
_MAX_DIAGNOSTICS = 32
_MAX_DIAGNOSTIC_CHARS = 1000
_PROCEDURAL_FAILURE = re.compile(
    r"(?:\bprocedural\b.*\b(?:error|failed|failure|unable)\b|"
    r"\b(?:error|failed|failure|unable)\b.*\bprocedural\b)",
    re.IGNORECASE,
)
_RENDERER_ERROR = re.compile(r"(?:^|\s)Error:\s*", re.IGNORECASE)
_RENDERER_WARNING = re.compile(r"(?:^|\s)Warning:\s*", re.IGNORECASE)


def _written_files(status: dict) -> list:
    written = [path for path in status.get("expected_outputs", []) if os.path.isfile(path)]
    if not written and status.get("output_glob"):
        written = sorted(path for path in glob.glob(str(status["output_glob"])) if os.path.isfile(path))
    return written


def _bounded_stderr(path_value) -> str:
    if not path_value:
        return ""
    try:
        with Path(str(path_value)).open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - _STDERR_SCAN_BYTES))
            payload = stream.read(_STDERR_SCAN_BYTES)
    except OSError:
        return ""
    return payload.decode("utf-8", errors="replace")


def _render_diagnostics(stderr: str):
    render_errors = []
    warnings = []
    for raw_line in stderr.splitlines():
        message = " ".join(raw_line.split())[:_MAX_DIAGNOSTIC_CHARS]
        if not message:
            continue
        if "hou.OperationFailed" in message:
            target = render_errors
            code = "HOUDINI_OPERATION_FAILED"
        elif _PROCEDURAL_FAILURE.search(message):
            target = render_errors
            code = "PROCEDURAL_INVOCATION_FAILED"
        elif _RENDERER_ERROR.search(message):
            target = render_errors
            code = "RENDERER_ERROR"
        elif _RENDERER_WARNING.search(message):
            target = warnings
            code = "RENDERER_WARNING"
        else:
            continue
        diagnostic = {"code": code, "message": message}
        if diagnostic not in target and len(target) < _MAX_DIAGNOSTICS:
            target.append(diagnostic)
    return render_errors, warnings


def main() -> None:
    status_path = Path(sys.argv[1])
    command = json.loads(sys.argv[2])
    status = read_status(status_path)
    status.setdefault("render_outcome", "pending")
    status.setdefault("render_errors", [])
    status.setdefault("warnings", [])
    started = time.time()
    status.update({"state": "running", "started_at": started, "worker_pid": os.getpid()})
    write_status(status_path, status)
    try:
        process = subprocess.run(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            timeout=int(status.get("timeout_secs") or 3600),
            check=False,
        )
        written_files = _written_files(status)
        render_errors, warnings = _render_diagnostics(_bounded_stderr(status.get("stderr_path")))
        if process.returncode != 0:
            state = "failed"
            render_outcome = "failed"
        elif render_errors:
            state = "failed"
            render_outcome = "completed_with_render_errors"
        elif warnings:
            state = "completed"
            render_outcome = "completed_with_warnings"
        else:
            state = "completed"
            render_outcome = "completed_clean"
        status.update(
            {
                "state": state,
                "render_outcome": render_outcome,
                "returncode": process.returncode,
                "render_errors": render_errors,
                "warnings": warnings,
                "written_files": written_files,
                "output_verification": {
                    "state": "verified" if written_files else "not_observed",
                    "expected_output_count": len(status.get("expected_outputs", [])),
                    "written_file_count": len(written_files),
                },
            }
        )
        if process.returncode != 0:
            status["error"] = "husk exited with code {}".format(process.returncode)
        elif render_errors:
            status["error"] = "Husk reported procedural or renderer errors"
    except subprocess.TimeoutExpired:
        status.update(
            {
                "state": "failed",
                "render_outcome": "failed",
                "error": "Husk render exceeded the configured timeout",
                "written_files": _written_files(status),
            }
        )
    except Exception as exc:  # noqa: BLE001
        status.update(
            {
                "state": "failed",
                "render_outcome": "failed",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "written_files": _written_files(status),
            }
        )
    finally:
        status["finished_at"] = time.time()
        status["elapsed_secs"] = round(status["finished_at"] - started, 3)
        write_status(status_path, status)


if __name__ == "__main__":
    main()
