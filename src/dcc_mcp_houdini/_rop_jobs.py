"""ROP-specific adapter for isolated Houdini jobs."""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_houdini import _isolated_jobs
from dcc_mcp_houdini._hip_file_state import get_hip_dirty_state
from dcc_mcp_houdini._render_artifacts import (
    TRANSACTION_MODE,
    aggregate_artifacts,
    assert_same_parent_and_volume,
    fsync_file,
    fsync_parent,
    identity_matches_receipt,
    integer_frames,
    normalize_transaction_request,
    publish_no_clobber,
    stable_file_identity,
    validate_receipt,
)

_SUMMARY_WARNING_LIMIT = 10
_SUMMARY_TEXT_LIMIT = 500
_STDERR_TAIL_BYTES = 256 * 1024


def _hython_executable() -> Path:
    executable_name = "hython.exe" if os.name == "nt" else "hython"
    executable = Path(sys.executable).with_name(executable_name)
    if not executable.is_file() and os.environ.get("HFS"):
        executable = Path(os.environ["HFS"]) / "bin" / executable_name
    if not executable.is_file():
        raise FileNotFoundError("hython executable was not found beside Houdini")
    return executable


def _validate_saved_hip(hou: Any) -> tuple:
    hip_path = Path(hou.hipFile.path())
    if not hip_path.is_file():
        raise ValueError("Background rendering requires the current HIP file to be saved")
    is_ui_available = bool(hou.isUIAvailable())
    dirty = get_hip_dirty_state(hou)
    if dirty is True:
        raise ValueError("Background rendering rejects unsaved changes; save the HIP file explicitly first")
    if is_ui_available and dirty is None:
        raise ValueError("Background rendering cannot determine the current HIP dirty state")
    return hip_path, is_ui_available


def _save_owned_hip_snapshot(hou: Any, job_dir: Path) -> Path:
    """Save a headless copy without changing or overwriting the current HIP."""
    backup_dir = hou.getenv("HOUDINI_BACKUP_DIR")
    snapshot_path = None
    hou.putenv("HOUDINI_BACKUP_DIR", str(job_dir))
    try:
        snapshot_path = Path(hou.hipFile.saveAsBackup())
    except Exception as exc:
        raise ValueError("Headless background rendering failed to create an isolated HIP snapshot") from exc
    finally:
        if backup_dir is None:
            hou.unsetenv("HOUDINI_BACKUP_DIR")
        else:
            hou.putenv("HOUDINI_BACKUP_DIR", backup_dir)
    if snapshot_path.resolve().parent != job_dir.resolve() or not snapshot_path.is_file():
        raise ValueError("Headless background rendering did not produce an owned HIP snapshot")
    return snapshot_path


def _remove_owned_hip_snapshot(status_path: Path, status: Dict[str, Any]) -> bool:
    """Remove only a snapshot located directly inside this job's directory."""
    if status.get("hip_snapshot_owned") is not True:
        return False
    snapshot_value = status.get("hip_path")
    if not snapshot_value:
        return False
    snapshot_path = Path(str(snapshot_value))
    if snapshot_path.resolve().parent != status_path.parent.resolve():
        return False
    try:
        snapshot_path.unlink()
    except FileNotFoundError:
        return False
    return True


def launch_background_render(
    hou: Any,
    rop_path: str,
    frame_range: Optional[List[float]],
    output_pattern: Optional[str],
    ignore_inputs: bool = False,
    job_kind: str = "render",
    artifact_transaction: Optional[dict] = None,
) -> Dict[str, Any]:
    """Launch one saved ROP job in an isolated hython process."""
    source_hip_path, is_ui_available = _validate_saved_hip(hou)
    executable = _hython_executable()
    transaction = None
    if artifact_transaction is not None:
        if job_kind != "render":
            raise ValueError("artifact_transaction supports render jobs only")
        transaction = normalize_transaction_request(artifact_transaction)
        transaction["requested_frames"] = integer_frames(frame_range)
    initial_payload = {
        "job_kind": job_kind,
        "hip_path": str(source_hip_path),
        "rop_path": rop_path,
        "frame_range": frame_range,
        "output_pattern": output_pattern,
        "ignore_inputs": bool(ignore_inputs),
    }
    if transaction is not None:
        initial_payload["artifact_transaction"] = transaction
    initial, status_path = _isolated_jobs.create_job(initial_payload)
    hip_path = source_hip_path
    if not is_ui_available:
        try:
            hip_path = _save_owned_hip_snapshot(hou, status_path.parent)
        except Exception as exc:
            initial.update({"state": "failed", "finished_at": time.time(), "error": str(exc)})
            if isinstance(initial.get("artifact_transaction"), dict):
                initial["artifact_transaction"]["state"] = "failed"
            _isolated_jobs.write_status(status_path, initial)
            raise
        initial.update(
            {
                "hip_path": str(hip_path),
                "source_hip_path": str(source_hip_path),
                "hip_snapshot_owned": True,
            }
        )
        _isolated_jobs.write_status(status_path, initial)
    worker_path = Path(__file__).resolve().parent / "skills" / "houdini-render" / "scripts" / "_render_worker.py"
    command = [
        str(executable),
        str(worker_path),
        str(hip_path),
        rop_path,
        json.dumps(frame_range),
        str(status_path),
        json.dumps(output_pattern),
        json.dumps(bool(ignore_inputs)),
    ]
    child_env = dict(os.environ)
    child_env["DCC_MCP_BACKGROUND_RENDER"] = "1"
    try:
        return _isolated_jobs.launch_job(initial["job_id"], command, child_env)
    except Exception:
        _remove_owned_hip_snapshot(status_path, initial)
        raise


def _file_signature(path: str) -> Optional[Dict[str, int]]:
    try:
        output = Path(path)
        file_stat = output.stat()
    except OSError:
        return None
    if not stat.S_ISREG(file_stat.st_mode):
        return None
    return {"mtime_ns": file_stat.st_mtime_ns, "size": file_stat.st_size}


def _with_progress(status: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(status)
    expected = list(result.get("expected_outputs") or [])
    before = dict(result.get("output_snapshot") or {})
    observed = []
    for output in expected:
        signature = _file_signature(output)
        if signature is not None and signature != before.get(output):
            observed.append(output)

    state = result.get("state")
    total = len(expected)
    if state in _isolated_jobs._TERMINAL_STATES and "written_files" in result:
        completed_outputs = list(result.get("written_files") or [])
        verification = result.get("output_verification") or {}
        worker_total = verification.get("expected_output_count")
        if isinstance(worker_total, int) and not isinstance(worker_total, bool) and worker_total >= 0:
            total = max(total, worker_total)
        total = max(total, len(completed_outputs))
    elif state == "completed":
        # Older workers did not persist written_files. A completed legacy job
        # has closed all of its observed outputs, so none remains in progress.
        completed_outputs = observed
    else:
        # Frame ranges emit expected outputs in order. The last observed file may
        # still be open, so hold it pending until the worker verifies it.
        completed_outputs = observed[:-1]

    completed = len(completed_outputs)
    result["completed"] = completed
    result["total"] = total
    result["progress"] = float(completed) / total if total else None
    if result.get("state") not in _isolated_jobs._TERMINAL_STATES or "written_files" not in result:
        result["written_files"] = completed_outputs

    started_at = result.get("started_at")
    if started_at is not None:
        finished_at = result.get("finished_at")
        elapsed = float(finished_at) - float(started_at) if finished_at is not None else time.time() - float(started_at)
        result["elapsed_secs"] = round(max(0.0, elapsed), 3)
    elapsed_secs = result.get("elapsed_secs")
    if state in {"failed", "cancelled", "interrupted"}:
        result["eta_secs"] = None
    elif state == "completed":
        result["eta_secs"] = 0.0 if total and completed >= total else None
    elif total and completed and elapsed_secs is not None:
        result["eta_secs"] = round(float(elapsed_secs) * (total - completed) / completed, 3)
    else:
        result["eta_secs"] = None
    return result


def _stderr_tail(status: Dict[str, Any]) -> str:
    """Read at most the bounded tail of the worker's stderr stream."""
    stderr_path = status.get("stderr_path")
    if not stderr_path:
        return ""

    try:
        with Path(str(stderr_path)).open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            offset = max(0, size - _STDERR_TAIL_BYTES)
            stream.seek(offset)
            payload = stream.read(_STDERR_TAIL_BYTES)
    except OSError:
        return ""
    if offset:
        newline = payload.find(b"\n")
        payload = payload[newline + 1 :] if newline >= 0 else b""
    return payload.decode("utf-8", errors="replace")


def _warning_lines(status: Dict[str, Any]) -> List[Any]:
    """Merge worker warnings with unique, non-empty stderr diagnostics."""
    raw_warnings = status.get("warnings", []) or []
    status_warnings = list(raw_warnings) if isinstance(raw_warnings, (list, tuple)) else [raw_warnings]
    warnings = []
    seen = set()
    for warning in status_warnings:
        normalized = " ".join(str(warning).splitlines())
        if normalized and normalized not in seen:
            seen.add(normalized)
            warnings.append(warning)
    # Houdini render diagnostics are not consistently prefixed with "Warning";
    # stderr is the worker's dedicated diagnostic stream, so retain every line.
    for raw_line in _stderr_tail(status).splitlines():
        warning = " ".join(raw_line.splitlines())
        if warning and warning not in seen:
            seen.add(warning)
            warnings.append(warning)
    return warnings


def _transaction_summary(transaction: Dict[str, Any]) -> Dict[str, Any]:
    return {key: transaction[key] for key in ("mode", "state", "output_parm_name", "aggregate") if key in transaction}


def _set_transaction(status: Dict[str, Any], transaction: Dict[str, Any]) -> None:
    transaction = dict(transaction)
    transaction["aggregate"] = aggregate_artifacts(transaction.get("artifacts", []))
    transaction["state"] = transaction["aggregate"]["state"]
    transaction["updated_at"] = time.time()
    status["artifact_transaction"] = transaction


def _revalidate_committed(transaction: Dict[str, Any]) -> tuple:
    artifacts = []
    errors = []
    for source in transaction.get("artifacts", []):
        artifact = dict(source)
        if artifact.get("committed") is True:
            expected = artifact.get("committed_identity")
            try:
                identity = stable_file_identity(artifact["final_path"])
                if not isinstance(expected, dict) or identity != expected:
                    raise ValueError("committed final output identity drifted")
            except Exception as exc:  # noqa: BLE001
                artifact["state"] = "drifted"
                artifact["post_commit_error"] = str(exc)
                errors.append("frame {}: {}".format(artifact.get("frame"), exc))
        artifacts.append(artifact)
    transaction = dict(transaction)
    transaction["artifacts"] = artifacts
    transaction["aggregate"] = aggregate_artifacts(artifacts)
    transaction["state"] = transaction["aggregate"]["state"]
    return transaction, errors


def _recover_publication_intents(job_id: str, transaction: Dict[str, Any]) -> tuple:
    """Resolve the narrow crash window between publication and status update."""
    artifacts = []
    errors = []
    for source in transaction.get("artifacts", []):
        artifact = dict(source)
        if artifact.get("state") != "publishing" or artifact.get("committed") is True:
            artifacts.append(artifact)
            continue
        try:
            receipt = validate_receipt(artifact.get("validator_receipt"), job_id, artifact)
            staged_exists = os.path.lexists(artifact["staging_path"])
            final_exists = os.path.lexists(artifact["final_path"])
            if not final_exists:
                if not staged_exists:
                    raise ValueError("publication intent lost both staged and final outputs")
                artifact["state"] = "staged"
                artifacts.append(artifact)
                continue
            final_identity = stable_file_identity(artifact["final_path"])
            if not identity_matches_receipt(final_identity, receipt):
                raise ValueError("publication intent final output does not match its validator receipt")
            cleanup_error = None
            if staged_exists:
                staged_identity = stable_file_identity(artifact["staging_path"])
                if not identity_matches_receipt(staged_identity, receipt) or not os.path.samefile(
                    artifact["staging_path"], artifact["final_path"]
                ):
                    raise FileExistsError("publication intent collided with an unrelated final output")
                try:
                    os.unlink(artifact["staging_path"])
                except OSError as exc:
                    cleanup_error = str(exc)
            try:
                fsync_parent(artifact["final_path"])
            except OSError as exc:
                cleanup_error = cleanup_error or str(exc)
            artifact.update(
                {
                    "committed": True,
                    "committed_identity": final_identity,
                    "state": "attention_required" if cleanup_error else "committed",
                    "cleanup_error": cleanup_error,
                    "recovered_at": time.time(),
                }
            )
            if cleanup_error:
                errors.append("frame {}: {}".format(artifact.get("frame"), cleanup_error))
        except Exception as exc:  # noqa: BLE001
            artifact["state"] = "collision" if isinstance(exc, FileExistsError) else "drifted"
            artifact["last_error"] = str(exc)
            errors.append("frame {}: {}".format(artifact.get("frame"), exc))
        artifacts.append(artifact)
    transaction = dict(transaction)
    transaction["artifacts"] = artifacts
    transaction["aggregate"] = aggregate_artifacts(artifacts)
    transaction["state"] = transaction["aggregate"]["state"]
    return transaction, errors


def _persist_finalize_failure(
    status_path: Path,
    status: Dict[str, Any],
    transaction: Dict[str, Any],
    artifact_index: int,
    state: str,
    error: Exception,
    committed: bool = False,
) -> None:
    artifacts = [dict(item) for item in transaction.get("artifacts", [])]
    artifact = artifacts[artifact_index]
    artifact.update(
        {
            "state": state,
            "committed": committed,
            "last_error": str(error),
            "last_error_at": time.time(),
        }
    )
    artifacts[artifact_index] = artifact
    transaction = dict(transaction)
    transaction["artifacts"] = artifacts
    _set_transaction(status, transaction)
    _isolated_jobs.write_status(status_path, status)


def finalize_render_outputs(job_id: str, validator_receipts: List[dict]) -> Dict[str, Any]:
    """Publish externally validated staged EXRs without replacing final paths."""
    if not isinstance(validator_receipts, list) or not validator_receipts:
        raise ValueError("validator_receipts must be a non-empty array")
    _isolated_jobs.read_job(job_id)
    status_path = _isolated_jobs._status_path(job_id)
    finalized_frames = []
    with _isolated_jobs._PROCESS_LOCK:
        status = _isolated_jobs._read_status(status_path)
        if status.get("state") != "completed":
            raise ValueError("render worker must be completed before finalization")
        transaction = status.get("artifact_transaction")
        if not isinstance(transaction, dict) or transaction.get("mode") != TRANSACTION_MODE:
            raise ValueError("render job has no staged_no_clobber artifact transaction")
        artifacts = transaction.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("render job has no staged artifacts")
        if len(validator_receipts) > len(artifacts):
            raise ValueError("validator_receipts exceeds the staged artifact count")

        transaction, recovery_errors = _recover_publication_intents(job_id, transaction)
        _set_transaction(status, transaction)
        _isolated_jobs.write_status(status_path, status)
        transaction = status["artifact_transaction"]
        if recovery_errors:
            raise ValueError("; ".join(recovery_errors))
        transaction, drift_errors = _revalidate_committed(transaction)
        if drift_errors:
            _set_transaction(status, transaction)
            _isolated_jobs.write_status(status_path, status)
            raise ValueError("; ".join(drift_errors))

        seen_frames = set()
        for receipt_payload in validator_receipts:
            frame = receipt_payload.get("frame") if isinstance(receipt_payload, dict) else None
            if isinstance(frame, bool) or not isinstance(frame, int) or frame in seen_frames:
                raise ValueError("validator_receipts must bind unique integer frames")
            seen_frames.add(frame)
            artifacts = [dict(item) for item in transaction["artifacts"]]
            matching = [index for index, artifact in enumerate(artifacts) if artifact.get("frame") == frame]
            if len(matching) != 1:
                raise ValueError("validator receipt frame is not part of this render job")
            artifact_index = matching[0]
            artifact = artifacts[artifact_index]
            receipt = validate_receipt(receipt_payload, job_id, artifact)

            if artifact.get("committed") is True:
                if artifact.get("validator_receipt") != receipt:
                    raise ValueError("committed frame validator receipt does not match")
                final_identity = stable_file_identity(artifact["final_path"])
                if not identity_matches_receipt(final_identity, receipt):
                    error = ValueError("committed final output no longer matches its validator receipt")
                    _persist_finalize_failure(
                        status_path,
                        status,
                        transaction,
                        artifact_index,
                        "drifted",
                        error,
                        committed=True,
                    )
                    raise error
                finalized_frames.append(frame)
                continue
            if artifact.get("state") != "staged":
                raise ValueError("frame {} is not in staged state".format(frame))

            try:
                assert_same_parent_and_volume(artifact["staging_path"], artifact["final_path"])
                staged_identity = stable_file_identity(artifact["staging_path"])
                if not identity_matches_receipt(staged_identity, receipt):
                    raise ValueError("staged output does not match its validator receipt")
                fsync_file(artifact["staging_path"])
                if stable_file_identity(artifact["staging_path"]) != staged_identity:
                    raise ValueError("staged output identity drifted after fsync")
            except Exception as exc:
                _persist_finalize_failure(
                    status_path,
                    status,
                    transaction,
                    artifact_index,
                    "drifted",
                    exc,
                )
                raise

            artifact.update(
                {
                    "state": "publishing",
                    "validator_receipt": receipt,
                    "publication_started_at": time.time(),
                }
            )
            artifacts[artifact_index] = artifact
            transaction["artifacts"] = artifacts
            _set_transaction(status, transaction)
            _isolated_jobs.write_status(status_path, status)
            transaction = status["artifact_transaction"]

            try:
                publication = publish_no_clobber(artifact["staging_path"], artifact["final_path"])
            except Exception as exc:
                failure_state = "collision" if isinstance(exc, FileExistsError) else "attention_required"
                _persist_finalize_failure(
                    status_path,
                    status,
                    transaction,
                    artifact_index,
                    failure_state,
                    exc,
                )
                raise

            artifacts = [dict(item) for item in transaction["artifacts"]]
            artifact = artifacts[artifact_index]
            artifact.update(
                {
                    "state": "post_commit_verification",
                    "committed": True,
                    "published_at": time.time(),
                    "publication_method": "rename" if os.name == "nt" else "hardlink_unlink",
                    "cleanup_error": publication.get("cleanup_error"),
                }
            )
            artifacts[artifact_index] = artifact
            transaction["artifacts"] = artifacts
            _set_transaction(status, transaction)
            _isolated_jobs.write_status(status_path, status)
            transaction = status["artifact_transaction"]

            final_identity = None
            try:
                final_identity = stable_file_identity(artifact["final_path"])
                if not identity_matches_receipt(final_identity, receipt):
                    raise ValueError("published final output does not match its validator receipt")
                fsync_parent(artifact["final_path"])
                if publication.get("cleanup_error"):
                    raise RuntimeError("staging cleanup failed: {}".format(publication["cleanup_error"]))
            except Exception as exc:
                artifacts = [dict(item) for item in transaction["artifacts"]]
                artifact = artifacts[artifact_index]
                if final_identity is not None:
                    artifact["committed_identity"] = final_identity
                artifact.update(
                    {
                        "state": "commit_verification_failed",
                        "committed": True,
                        "post_commit_error": str(exc),
                        "post_commit_checked_at": time.time(),
                    }
                )
                artifacts[artifact_index] = artifact
                transaction["artifacts"] = artifacts
                _set_transaction(status, transaction)
                _isolated_jobs.write_status(status_path, status)
                raise

            artifacts = [dict(item) for item in transaction["artifacts"]]
            artifact = artifacts[artifact_index]
            artifact.update(
                {
                    "state": "committed",
                    "committed": True,
                    "committed_identity": final_identity,
                    "post_commit_verified_at": time.time(),
                }
            )
            artifacts[artifact_index] = artifact
            transaction["artifacts"] = artifacts
            _set_transaction(status, transaction)
            _isolated_jobs.write_status(status_path, status)
            transaction = status["artifact_transaction"]
            finalized_frames.append(frame)

        transaction, drift_errors = _revalidate_committed(transaction)
        _set_transaction(status, transaction)
        _isolated_jobs.write_status(status_path, status)
        if drift_errors:
            raise ValueError("; ".join(drift_errors))
        transaction = status["artifact_transaction"]
        return {
            "job_id": job_id,
            "worker_state": status["state"],
            "transaction_state": transaction["state"],
            "aggregate": transaction["aggregate"],
            "finalized_frames": finalized_frames,
        }


def read_render_job(job_id: str, include_details: bool = False) -> Dict[str, Any]:
    result = _with_progress(_isolated_jobs.read_job(job_id))
    if result.get("state") in _isolated_jobs._TERMINAL_STATES:
        _remove_owned_hip_snapshot(_isolated_jobs._status_path(job_id), result)
    warnings = _warning_lines(result)
    result["warning_count"] = len(warnings)
    if include_details:
        result["warnings"] = warnings
    if not include_details:
        transaction = result.get("artifact_transaction")
        if isinstance(transaction, dict):
            result["artifact_transaction"] = _transaction_summary(transaction)
        result.pop("expected_outputs", None)
        result.pop("output_snapshot", None)
        written_files = list(result.pop("written_files", []) or [])
        result["written_file_count"] = len(written_files)
        result["recent_written_files"] = written_files[-10:]
        result.pop("warnings", None)
        result["recent_warnings"] = [
            " ".join(str(warning).splitlines())[:_SUMMARY_TEXT_LIMIT] for warning in warnings[-_SUMMARY_WARNING_LIMIT:]
        ]
        result.pop("traceback", None)
        error = result.pop("error", None)
        if error:
            result["error_summary"] = " ".join(str(error).splitlines())[:_SUMMARY_TEXT_LIMIT]
    return result


def cancel_render_job(job_id: str, terminate: Any = None) -> Dict[str, Any]:
    result = _isolated_jobs.cancel_job(job_id, terminate=terminate)
    if result.get("state") in _isolated_jobs._TERMINAL_STATES:
        _remove_owned_hip_snapshot(_isolated_jobs._status_path(job_id), result)
    return result
