"""Isolated hython worker used by background ROP jobs."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from _render_common import expanded_outputs, output_snapshot, render_node, requested_outputs, updated_outputs


def write_status(path: Path, payload: dict) -> None:
    """Atomically replace worker status without importing the adapter package."""
    pending = path.with_name("{}.{}.tmp".format(path.name, os.getpid()))
    pending.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(str(pending), str(path))


def _cook_errors(status: dict) -> list:
    """Return cook-error lines emitted by this job."""
    sys.stdout.flush()
    sys.stderr.flush()
    lines = []
    for key in ("stdout_path", "stderr_path"):
        path = Path(status.get(key, ""))
        if path.is_file():
            lines.extend(
                line.strip()
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                if "cook error" in line.lower()
            )
    return lines


def _remove_owned_hip_snapshot(status_path: Path, status: dict, hip_path: Path) -> None:
    """Remove only the snapshot created inside this job's directory."""
    if status.get("hip_snapshot_owned") is True and hip_path.resolve().parent == status_path.parent.resolve():
        try:
            hip_path.unlink()
        except FileNotFoundError:
            pass


def _verify_outputs(candidates: list, before: dict, output_pattern) -> tuple:
    written_files = updated_outputs(candidates, before)
    verification_state = "not_observed"
    if written_files:
        verification_state = "verified" if len(written_files) == len(candidates) else "partial"
    if not output_pattern:
        verification_state = "unavailable"
    return written_files, {
        "state": verification_state,
        "expected_output_count": len(candidates),
        "written_file_count": len(written_files),
    }


def main() -> None:
    import hou  # Lazy import: requires Houdini's embedded Python.

    hip_arg, rop_path, range_json, status_arg, output_json = sys.argv[1:6]
    ignore_inputs = json.loads(sys.argv[6]) if len(sys.argv) > 6 else False
    hip_path = Path(hip_arg)
    status_path = Path(status_arg)
    frame_range = json.loads(range_json)
    output_pattern = json.loads(output_json)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    started = time.time()
    status.update({"state": "running", "pid": os.getpid(), "started_at": started})
    write_status(status_path, status)
    written_files = []
    rop_errors = []
    output_verification = {
        "state": "pending",
        "expected_output_count": 0,
        "written_file_count": 0,
    }
    verification_ready = False
    try:
        hou.hipFile.load(str(hip_path), suppress_save_prompt=True)
        if status.get("hip_snapshot_owned") is True:
            hou.hipFile.setName(status["source_hip_path"])
            _remove_owned_hip_snapshot(status_path, status, hip_path)
        rop = hou.node(rop_path)
        if rop is None:
            raise ValueError("ROP node not found: {}".format(rop_path))
        expected_outputs = (
            status["expected_outputs"]
            if frame_range and "expected_outputs" in status
            else requested_outputs(hou, output_pattern, frame_range)
        )
        before = status.get("output_snapshot")
        if before is None:
            before = output_snapshot(expected_outputs)
        status.update({"expected_outputs": expected_outputs, "output_snapshot": before})
        write_status(status_path, status)
        verification_ready = True
        if ignore_inputs:
            _, execution_mode = render_node(rop, frame_range, ignore_inputs=True)
        else:
            _, execution_mode = render_node(rop, frame_range)
        rop_errors = [str(error) for error in rop.errors()] if hasattr(rop, "errors") else []
        logged_cook_errors = _cook_errors(status)
        candidates = expected_outputs if frame_range else expanded_outputs(output_pattern)
        written_files, output_verification = _verify_outputs(candidates, before, output_pattern)
        if logged_cook_errors:
            raise RuntimeError("ROP cook error: {}".format("; ".join(logged_cook_errors[:3])))
        if rop_errors:
            raise RuntimeError("ROP errors: {}".format("; ".join(rop_errors)))
        if not written_files and status.get("job_kind", "render") != "rop_chain":
            raise RuntimeError("Render produced no new or updated output for the requested frame range")
        status.update(
            {
                "state": "completed",
                "execution_mode": execution_mode,
                "elapsed_secs": round(time.time() - started, 3),
                "written_files": written_files,
                "output_verification": output_verification,
                "warnings": [],
            }
        )
    except Exception as exc:  # noqa: BLE001
        if verification_ready:
            candidates = expected_outputs if frame_range else expanded_outputs(output_pattern)
            written_files, output_verification = _verify_outputs(candidates, before, output_pattern)
        status.update(
            {
                "state": "failed",
                "elapsed_secs": round(time.time() - started, 3),
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "written_files": written_files,
                "output_verification": output_verification,
                "warnings": rop_errors,
            }
        )
    finally:
        _remove_owned_hip_snapshot(status_path, status, hip_path)
        status["finished_at"] = time.time()
        write_status(status_path, status)


if __name__ == "__main__":
    main()
