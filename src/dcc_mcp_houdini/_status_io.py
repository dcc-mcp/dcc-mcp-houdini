"""Pure-stdlib atomic JSON status I/O shared by adapter and workers."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

_STATUS_IO_TIMEOUT_SECONDS = 1.0
_STATUS_IO_POLL_SECONDS = 0.01


def _retry_windows_status_io(operation: Callable[[], Any], description: str) -> Any:
    """Retry transient Windows sharing violations within one bounded deadline."""
    if os.name != "nt":
        return operation()
    deadline = time.monotonic() + _STATUS_IO_TIMEOUT_SECONDS
    while True:
        try:
            return operation()
        except PermissionError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out while {}".format(description)) from exc
            time.sleep(min(_STATUS_IO_POLL_SECONDS, remaining))


def _remove_pending_status(path: Path) -> None:
    try:
        _retry_windows_status_io(path.unlink, "cleaning pending status file {}".format(path))
    except FileNotFoundError:
        pass


def write_status(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically replace one JSON status document without exposing partial JSON."""
    pending = path.with_name("{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    try:
        pending.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
        _retry_windows_status_io(
            lambda: os.replace(str(pending), str(path)),
            "replacing status file {}".format(path),
        )
    except Exception:
        try:
            _remove_pending_status(pending)
        except Exception:  # noqa: BLE001
            pass
        raise


def read_status(path: Path) -> Dict[str, Any]:
    """Read and decode one complete atomic status document."""
    payload = _retry_windows_status_io(
        lambda: path.read_text(encoding="utf-8"),
        "reading status file {}".format(path),
    )
    return json.loads(payload)
