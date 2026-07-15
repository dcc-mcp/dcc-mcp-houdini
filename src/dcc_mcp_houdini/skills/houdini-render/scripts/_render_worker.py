"""Isolated hython worker used by background ROP jobs."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from _render_common import expanded_outputs, render_node


def write_status(path: Path, payload: dict) -> None:
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(str(pending), str(path))


def main() -> None:
    import hou  # Lazy import: requires Houdini's embedded Python.

    hip_path, rop_path, range_json, status_arg, output_json = sys.argv[1:6]
    status_path = Path(status_arg)
    frame_range = json.loads(range_json)
    output_pattern = json.loads(output_json)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    started = time.time()
    status.update({"state": "running", "pid": os.getpid(), "started_at": started})
    write_status(status_path, status)
    try:
        hou.hipFile.load(hip_path, suppress_save_prompt=True)
        rop = hou.node(rop_path)
        if rop is None:
            raise ValueError("ROP node not found: {}".format(rop_path))
        _, execution_mode = render_node(rop, frame_range)
        status.update(
            {
                "state": "completed",
                "execution_mode": execution_mode,
                "elapsed_secs": round(time.time() - started, 3),
                "written_files": expanded_outputs(output_pattern),
                "warnings": list(rop.errors()) if hasattr(rop, "errors") else [],
            }
        )
    except Exception as exc:  # noqa: BLE001
        status.update(
            {
                "state": "failed",
                "elapsed_secs": round(time.time() - started, 3),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        status["finished_at"] = time.time()
        write_status(status_path, status)


if __name__ == "__main__":
    main()
