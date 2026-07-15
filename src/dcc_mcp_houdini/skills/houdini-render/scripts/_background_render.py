"""Launch and inspect isolated hython render jobs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import output_snapshot, requested_outputs


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(str(pending), str(path))


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
    expected_outputs = requested_outputs(hou, output_pattern, frame_range)
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
    status = dict(initial)
    status.update(
        {
            "expected_outputs": expected_outputs,
            "output_snapshot": output_snapshot(expected_outputs),
        }
    )
    _write_json(status_path, status)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            cwd=str(job_dir),
            creationflags=creationflags,
            close_fds=True,
        )
    initial.update({"pid": process.pid})
    return initial


def read_render_job(job_id: str) -> dict[str, Any]:
    if not job_id or any(char not in "0123456789abcdef" for char in job_id.lower()):
        raise ValueError("job_id must be a hexadecimal identifier")
    status_path = Path(tempfile.gettempdir()) / "dcc-mcp-houdini-render-jobs" / job_id / "status.json"
    if not status_path.is_file():
        raise FileNotFoundError("Render job was not found")
    return json.loads(status_path.read_text(encoding="utf-8"))
