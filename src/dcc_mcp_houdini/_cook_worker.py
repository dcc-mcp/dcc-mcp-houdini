"""Isolated hython worker for durable node cooks."""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from dcc_mcp_houdini._status_io import read_status, write_status


def _messages(node, method_name: str) -> list:
    method = getattr(node, method_name, None)
    if not callable(method):
        return []
    try:
        return list(method())
    except Exception:  # noqa: BLE001
        return []


def main() -> None:
    import hou

    hip_arg, node_path, force_arg, status_arg = sys.argv[1:5]
    status_path = Path(status_arg)
    status = read_status(status_path)
    status.update({"state": "running", "started_at": time.time(), "worker_pid": __import__("os").getpid()})
    write_status(status_path, status)
    try:
        hou.hipFile.load(hip_arg, suppress_save_prompt=True, ignore_load_warnings=True)
        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node does not exist: {}".format(node_path))
        node.cook(force=force_arg == "1")
        status.update(
            {
                "state": "completed",
                "finished_at": time.time(),
                "errors": _messages(node, "errors"),
                "warnings": _messages(node, "warnings"),
            }
        )
    except Exception as exc:  # noqa: BLE001
        status.update(
            {
                "state": "failed",
                "finished_at": time.time(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    if "started_at" in status:
        status["elapsed_secs"] = round(status["finished_at"] - status["started_at"], 3)
    write_status(status_path, status)


if __name__ == "__main__":
    main()
