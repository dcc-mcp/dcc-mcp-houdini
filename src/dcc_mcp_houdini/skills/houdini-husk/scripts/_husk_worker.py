"""Isolated hython worker that owns one blocking Husk process."""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from dcc_mcp_houdini._status_io import read_status, write_status


def _written_files(status: dict) -> list:
    written = [path for path in status.get("expected_outputs", []) if os.path.isfile(path)]
    if not written and status.get("output_glob"):
        written = sorted(path for path in glob.glob(str(status["output_glob"])) if os.path.isfile(path))
    return written


def main() -> None:
    status_path = Path(sys.argv[1])
    command = json.loads(sys.argv[2])
    status = read_status(status_path)
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
        status.update(
            {
                "state": "completed" if process.returncode == 0 else "failed",
                "returncode": process.returncode,
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
    except subprocess.TimeoutExpired:
        status.update(
            {
                "state": "failed",
                "error": "Husk render exceeded the configured timeout",
                "written_files": _written_files(status),
            }
        )
    except Exception as exc:  # noqa: BLE001
        status.update(
            {
                "state": "failed",
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
