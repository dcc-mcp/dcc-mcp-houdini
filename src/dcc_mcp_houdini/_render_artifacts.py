"""Staged, identity-bound publication helpers for isolated render outputs."""

from __future__ import annotations

import hashlib
import math
import os
import stat
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

TRANSACTION_MODE = "staged_no_clobber"
MAX_TRANSACTION_FRAMES = 100000
_REPARSE_POINT = 0x400
_SHA256_HEX_LENGTH = 64


class PublicationIdentityMismatchError(ValueError):
    """Publication completed, but ownership of the final path is unprovable."""


def normalize_transaction_request(value: Any) -> Dict[str, Any]:
    """Validate the opt-in request while keeping the legacy path untouched."""
    if not isinstance(value, Mapping):
        raise ValueError("artifact_transaction must be an object")
    unknown = sorted(set(value) - {"mode"})
    if unknown:
        raise ValueError("artifact_transaction has unsupported fields: {}".format(", ".join(unknown)))
    if value.get("mode") != TRANSACTION_MODE:
        raise ValueError("artifact_transaction.mode must be staged_no_clobber")
    return {
        "mode": TRANSACTION_MODE,
        "state": "queued",
        "artifacts": [],
        "aggregate": aggregate_artifacts([]),
    }


def integer_frames(frame_range: Optional[Sequence[float]]) -> list:
    """Expand an explicit integral frame range used by one-file-per-frame jobs."""
    if not frame_range or len(frame_range) not in (2, 3):
        raise ValueError("artifact_transaction requires frame_range with two or three values")
    values = list(frame_range)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ValueError("artifact_transaction frame_range values must be numbers")
    if any(isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()) for value in values):
        raise ValueError("artifact_transaction supports integral frames only")
    start, end = int(values[0]), int(values[1])
    step = int(values[2]) if len(values) == 3 else 1
    if step == 0 or (end - start) * step < 0:
        raise ValueError("frame_range step must move from start toward end")
    frame_count = (abs(end - start) // abs(step)) + 1
    if frame_count > MAX_TRANSACTION_FRAMES:
        raise ValueError("artifact_transaction supports at most {} frames".format(MAX_TRANSACTION_FRAMES))
    stop = end + (1 if step > 0 else -1)
    frames = list(range(start, stop, step))
    if not frames:
        raise ValueError("artifact_transaction frame_range produced no frames")
    return frames


def staging_pattern(final_pattern: str, job_id: str) -> str:
    """Place a unique staging EXR beside the final output for atomic publication."""
    if not isinstance(final_pattern, str) or not final_pattern.lower().endswith(".exr"):
        raise ValueError("artifact_transaction requires one EXR output pattern")
    if not job_id or any(char not in "0123456789abcdef" for char in job_id.lower()):
        raise ValueError("job_id must be a hexadecimal identifier")
    return "{}.dcc-mcp-{}.partial{}".format(final_pattern[:-4], job_id, final_pattern[-4:])


def _is_reparse(file_stat: os.stat_result) -> bool:
    return bool(getattr(file_stat, "st_file_attributes", 0) & _REPARSE_POINT)


def _absolute(path: Any) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def assert_no_links_or_reparse(path: Any) -> None:
    """Reject symlinks and Windows reparse points in every existing component."""
    current = _absolute(path)
    while True:
        try:
            file_stat = os.lstat(str(current))
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(file_stat.st_mode) or _is_reparse(file_stat):
                raise ValueError("artifact paths cannot contain symlinks or reparse points")
        parent = current.parent
        if parent == current:
            return
        current = parent


def assert_same_parent_and_volume(staged_path: Any, final_path: Any) -> None:
    """Require staging and final names to share one real directory and volume."""
    staged = _absolute(staged_path)
    final = _absolute(final_path)
    if os.path.normcase(str(staged.parent)) != os.path.normcase(str(final.parent)):
        raise ValueError("staging and final outputs must share one directory")
    assert_no_links_or_reparse(staged)
    assert_no_links_or_reparse(final)
    parent_stat = os.stat(str(final.parent), follow_symlinks=False)
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise ValueError("artifact output directory does not exist")
    try:
        staged_stat = os.lstat(str(staged))
    except FileNotFoundError:
        return
    if staged_stat.st_dev != parent_stat.st_dev:
        raise ValueError("staging and final outputs must be on the same volume")


def _fingerprint(file_stat: os.stat_result) -> tuple:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    )


def _assert_regular(file_stat: os.stat_result) -> None:
    if not stat.S_ISREG(file_stat.st_mode) or _is_reparse(file_stat):
        raise ValueError("artifact output must be a regular non-reparse file")


def stable_file_identity(path: Any) -> Dict[str, Any]:
    """Hash one regular file and fail if its path or handle identity drifts."""
    absolute = _absolute(path)
    assert_no_links_or_reparse(absolute)
    path_before = os.lstat(str(absolute))
    _assert_regular(path_before)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(absolute), flags)
    try:
        handle_before = os.fstat(descriptor)
        _assert_regular(handle_before)
        if _fingerprint(handle_before) != _fingerprint(path_before):
            raise ValueError("artifact identity changed before hashing")
        digest = hashlib.sha256()
        while True:
            payload = os.read(descriptor, 1024 * 1024)
            if not payload:
                break
            digest.update(payload)
        handle_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_after = os.lstat(str(absolute))
    _assert_regular(path_after)
    if _fingerprint(handle_before) != _fingerprint(handle_after) or _fingerprint(handle_after) != _fingerprint(
        path_after
    ):
        raise ValueError("artifact identity changed while hashing")
    return {
        "bytes": path_after.st_size,
        "mtime_ns": path_after.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def fsync_file(path: Any) -> None:
    """Flush staged bytes before the no-clobber publication boundary."""
    flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(_absolute(path)), flags)
    try:
        _assert_regular(os.fstat(descriptor))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_parent(path: Any, platform_name: Optional[str] = None) -> None:
    """Flush the containing directory on POSIX; Windows rename is the boundary."""
    if (platform_name or os.name) == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(str(_absolute(path).parent), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_no_clobber(
    staged_path: Any,
    final_path: Any,
    platform_name: Optional[str] = None,
    expected_identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Commit with native no-clobber semantics and never fall back to replace."""
    staged = _absolute(staged_path)
    final = _absolute(final_path)
    assert_same_parent_and_volume(staged, final)
    if os.path.lexists(str(final)):
        raise FileExistsError("final output already exists: {}".format(final))
    expected = dict(expected_identity) if expected_identity is not None else None
    if expected is not None and stable_file_identity(staged) != expected:
        raise ValueError("staged output identity changed before publication")
    cleanup_error = None
    if (platform_name or os.name) == "nt":
        os.rename(str(staged), str(final))
    else:
        os.link(str(staged), str(final), follow_symlinks=False)
    if expected is not None:
        try:
            published_identity = stable_file_identity(final)
        except Exception as exc:
            raise PublicationIdentityMismatchError(
                "published final identity could not be verified; final ownership is unprovable"
            ) from exc
        if published_identity != expected:
            raise PublicationIdentityMismatchError(
                "published final identity does not match the expected staged identity; final ownership is unprovable"
            )
    if (platform_name or os.name) != "nt":
        try:
            os.unlink(str(staged))
        except OSError as exc:
            cleanup_error = str(exc)
    return {"committed": True, "cleanup_error": cleanup_error}


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("{} must be a non-empty bounded string".format(field))
    return value


def _require_sha256(value: Any, field: str) -> str:
    value = _require_text(value, field).lower()
    if len(value) != _SHA256_HEX_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("{} must be a SHA-256 hex digest".format(field))
    return value


def validate_receipt(
    receipt: Any,
    job_id: str,
    artifact: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bind external validation to one exact staged file and final destination."""
    if not isinstance(receipt, Mapping):
        raise ValueError("validator receipt must be an object")
    if receipt.get("accepted") is not True:
        raise ValueError("validator receipt must set accepted=true")
    if receipt.get("job_id") != job_id:
        raise ValueError("validator receipt job_id does not match")
    frame = receipt.get("frame")
    if isinstance(frame, bool) or not isinstance(frame, int) or frame != artifact.get("frame"):
        raise ValueError("validator receipt frame does not match")
    for field in ("staging_path", "final_path"):
        if receipt.get(field) != artifact.get(field):
            raise ValueError("validator receipt {} does not match".format(field))
    byte_count = receipt.get("bytes")
    mtime_ns = receipt.get("mtime_ns")
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count <= 0:
        raise ValueError("validator receipt bytes must be a positive integer")
    if isinstance(mtime_ns, bool) or not isinstance(mtime_ns, int) or mtime_ns < 0:
        raise ValueError("validator receipt mtime_ns must be a non-negative integer")
    validator = receipt.get("validator")
    if not isinstance(validator, Mapping):
        raise ValueError("validator receipt validator must be an object")
    return {
        "accepted": True,
        "job_id": job_id,
        "frame": frame,
        "staging_path": artifact["staging_path"],
        "final_path": artifact["final_path"],
        "bytes": byte_count,
        "mtime_ns": mtime_ns,
        "sha256": _require_sha256(receipt.get("sha256"), "validator receipt sha256"),
        "validator": {
            "id": _require_text(validator.get("id"), "validator id"),
            "version": _require_text(validator.get("version"), "validator version"),
            "implementation_sha256": _require_sha256(
                validator.get("implementation_sha256"), "validator implementation_sha256"
            ),
        },
    }


def identity_matches_receipt(identity: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    return all(identity.get(field) == receipt.get(field) for field in ("bytes", "mtime_ns", "sha256"))


def aggregate_artifacts(artifacts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return one bounded publication aggregate for job polling."""
    total = len(artifacts)
    committed = sum(1 for artifact in artifacts if artifact.get("committed") is True)
    verified = sum(
        1 for artifact in artifacts if artifact.get("committed") is True and artifact.get("state") == "committed"
    )
    staged = sum(1 for artifact in artifacts if artifact.get("state") == "staged")
    failed = sum(
        1
        for artifact in artifacts
        if artifact.get("state")
        in {
            "attention_required",
            "cancelled",
            "collision",
            "commit_verification_failed",
            "drifted",
            "interrupted",
            "missing",
            "render_failed",
        }
    )
    complete = bool(total) and verified == total
    if complete:
        state = "committed"
    elif failed:
        state = "blocked"
    elif committed:
        state = "partially_committed"
    elif total and staged == total:
        state = "staged"
    elif total:
        state = "pending"
    else:
        state = "queued"
    return {
        "state": state,
        "total": total,
        "staged": staged,
        "committed": committed,
        "verified_committed": verified,
        "failed": failed,
        "pending": max(0, total - verified - failed),
        "complete": complete,
    }
