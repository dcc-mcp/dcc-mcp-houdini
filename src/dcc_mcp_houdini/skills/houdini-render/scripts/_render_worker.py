"""Isolated hython worker used by background ROP jobs."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from _render_common import (
    PRIMARY_OUTPUT_PARMS,
    expand_output_variables,
    expanded_outputs,
    output_snapshot,
    render_node,
    requested_outputs,
    updated_outputs,
)

from dcc_mcp_houdini._render_artifacts import (
    aggregate_artifacts,
    assert_same_parent_and_volume,
    integer_frames,
    staging_pattern,
)
from dcc_mcp_houdini._status_io import read_status, write_status


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
    written_files = []
    for output in updated_outputs(candidates, before):
        try:
            with Path(output).open("rb") as stream:
                if stream.read(1):
                    written_files.append(output)
        except OSError:
            continue
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


def _primary_exr_output(rop) -> tuple:
    candidates = []
    for name in PRIMARY_OUTPUT_PARMS:
        parm = rop.parm(name)
        if parm is None:
            continue
        try:
            pattern = parm.unexpandedString()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(pattern, str) and pattern.strip() and pattern.lower().endswith(".exr"):
            candidates.append((name, parm, pattern))
    if len(candidates) != 1:
        raise ValueError("artifact_transaction requires exactly one primary EXR output parameter")
    return candidates[0]


def _prepare_artifact_transaction(hou, rop, status: dict, frame_range) -> tuple:
    transaction = dict(status["artifact_transaction"])
    frames = integer_frames(frame_range)
    if transaction.get("requested_frames") != frames:
        raise ValueError("artifact_transaction requested frame contract changed before worker execution")
    inputs = getattr(rop, "inputs", None)
    if callable(inputs) and any(inputs()):
        raise ValueError("artifact_transaction does not support ROP input chains")
    output_parm_name, output_parm, final_pattern = _primary_exr_output(rop)
    staged_pattern = staging_pattern(final_pattern, status["job_id"])
    artifacts = []
    seen_final = set()
    seen_staged = set()
    for frame in frames:
        final_path = hou.text.expandStringAtFrame(final_pattern, frame)
        staged_path = hou.text.expandStringAtFrame(staged_pattern, frame)
        if not isinstance(final_path, str) or not isinstance(staged_path, str):
            raise ValueError("artifact_transaction output expansion must return paths")
        if not os.path.isabs(final_path) or not os.path.isabs(staged_path):
            raise ValueError("artifact_transaction outputs must resolve to absolute paths")
        final_path = os.path.abspath(final_path)
        staged_path = os.path.abspath(staged_path)
        final_key = os.path.normcase(final_path)
        staged_key = os.path.normcase(staged_path)
        if final_key in seen_final or staged_key in seen_staged:
            raise ValueError("artifact_transaction requires one unique EXR per frame")
        seen_final.add(final_key)
        seen_staged.add(staged_key)
        assert_same_parent_and_volume(staged_path, final_path)
        if os.path.lexists(final_path):
            raise FileExistsError("final output already exists: {}".format(final_path))
        if os.path.lexists(staged_path):
            raise FileExistsError("staging output already exists: {}".format(staged_path))
        artifacts.append(
            {
                "frame": frame,
                "staging_path": staged_path,
                "final_path": final_path,
                "state": "rendering",
                "committed": False,
            }
        )
    transaction.update(
        {
            "state": "rendering",
            "output_parm_name": output_parm_name,
            "final_output_pattern": final_pattern,
            "staging_output_pattern": staged_pattern,
            "artifacts": artifacts,
            "aggregate": aggregate_artifacts(artifacts),
        }
    )
    return transaction, output_parm, final_pattern, staged_pattern


def _observe_transaction_outputs(transaction: dict, written_files: list, worker_succeeded: bool) -> dict:
    written = {os.path.normcase(os.path.abspath(path)) for path in written_files}
    artifacts = []
    for source in transaction.get("artifacts", []):
        artifact = dict(source)
        staged_path = artifact["staging_path"]
        if os.path.normcase(os.path.abspath(staged_path)) in written:
            file_stat = os.lstat(staged_path)
            artifact["worker_observation"] = {
                "bytes": file_stat.st_size,
                "mtime_ns": file_stat.st_mtime_ns,
            }
            artifact["state"] = "staged" if worker_succeeded else "render_failed"
        else:
            artifact["state"] = "missing" if worker_succeeded else "render_failed"
        artifacts.append(artifact)
    transaction = dict(transaction)
    transaction["artifacts"] = artifacts
    transaction["state"] = (
        "staged"
        if worker_succeeded and all(artifact.get("state") == "staged" for artifact in artifacts)
        else "render_failed"
    )
    transaction["aggregate"] = aggregate_artifacts(artifacts)
    return transaction


def main() -> None:
    import hou  # Lazy import: requires Houdini's embedded Python.

    hip_arg, rop_path, range_json, status_arg, output_json = sys.argv[1:6]
    ignore_inputs = json.loads(sys.argv[6]) if len(sys.argv) > 6 else False
    hip_path = Path(hip_arg)
    status_path = Path(status_arg)
    frame_range = json.loads(range_json)
    output_pattern = json.loads(output_json)
    status = read_status(status_path)
    transaction_enabled = isinstance(status.get("artifact_transaction"), dict)
    transaction = dict(status.get("artifact_transaction") or {})
    output_parm = None
    original_output_pattern = None
    resolved_output_pattern = output_pattern
    expected_outputs = []
    before = {}
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
        resolved_output_pattern = output_pattern
        if not frame_range:
            resolved_output_pattern = expand_output_variables(hou, output_pattern)
        rop = hou.node(rop_path)
        if rop is None:
            raise ValueError("ROP node not found: {}".format(rop_path))
        if transaction_enabled:
            transaction, output_parm, original_output_pattern, resolved_output_pattern = _prepare_artifact_transaction(
                hou, rop, status, frame_range
            )
            status["artifact_transaction"] = transaction
            write_status(status_path, status)
            output_parm.set(resolved_output_pattern)
            expected_outputs = [artifact["staging_path"] for artifact in transaction["artifacts"]]
            before = {}
        else:
            expected_outputs = (
                status["expected_outputs"]
                if frame_range and "expected_outputs" in status
                else requested_outputs(hou, resolved_output_pattern, frame_range)
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
        candidates = expected_outputs if frame_range else expanded_outputs(resolved_output_pattern)
        written_files, output_verification = _verify_outputs(candidates, before, resolved_output_pattern)
        if logged_cook_errors:
            raise RuntimeError("ROP cook error: {}".format("; ".join(logged_cook_errors[:3])))
        if rop_errors:
            raise RuntimeError("ROP errors: {}".format("; ".join(rop_errors)))
        if (
            frame_range
            and output_verification["state"] == "partial"
            and status.get("job_kind", "render") != "rop_chain"
        ):
            raise RuntimeError(
                "Render produced {} of {} expected outputs".format(
                    output_verification["written_file_count"],
                    output_verification["expected_output_count"],
                )
            )
        if not written_files and status.get("job_kind", "render") != "rop_chain":
            raise RuntimeError("Render produced no new or updated output for the requested frame range")
        if transaction_enabled:
            transaction = _observe_transaction_outputs(transaction, written_files, worker_succeeded=True)
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
        if transaction_enabled:
            status["artifact_transaction"] = transaction
    except Exception as exc:  # noqa: BLE001
        if verification_ready:
            candidates = expected_outputs if frame_range else expanded_outputs(resolved_output_pattern)
            written_files, output_verification = _verify_outputs(candidates, before, resolved_output_pattern)
            if output_verification["state"] == "verified":
                output_verification["state"] = "failed"
        if transaction_enabled:
            transaction = _observe_transaction_outputs(
                transaction or status.get("artifact_transaction", {}),
                written_files,
                worker_succeeded=False,
            )
            transaction["state"] = "render_failed"
            transaction["worker_error"] = str(exc)
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
        if transaction_enabled:
            status["artifact_transaction"] = transaction
    finally:
        if output_parm is not None and original_output_pattern is not None:
            try:
                output_parm.set(original_output_pattern)
            except Exception as exc:  # noqa: BLE001
                status.setdefault("artifact_transaction", {})["override_restore_error"] = str(exc)
        _remove_owned_hip_snapshot(status_path, status, hip_path)
        status["finished_at"] = time.time()
        write_status(status_path, status)


if __name__ == "__main__":
    main()
