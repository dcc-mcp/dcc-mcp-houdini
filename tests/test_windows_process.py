"""Windows process boundary regressions."""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from dcc_mcp_houdini import _windows_process

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows process boundary")


def test_unopenable_descendant_handle_is_a_hard_failure() -> None:
    """Access denied on a descendant handle is surfaced, never silently skipped."""
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = 0
    known_pids = {4321}
    handles: dict = {}

    with patch.object(_windows_process, "_snapshot_processes", return_value=[(4321, 4), (4322, 4321)]), patch.object(
        _windows_process.ctypes, "get_last_error", return_value=_windows_process._ERROR_ACCESS_DENIED
    ), pytest.raises(RuntimeError, match="Failed to open an owned background process"):
        _windows_process._capture_descendant_handles(kernel32, known_pids, handles)

    assert handles == {}
    assert known_pids == {4321, 4322}


def test_exited_descendant_handle_is_skipped() -> None:
    """A descendant that exits mid-snapshot reports ERROR_INVALID_PARAMETER and is ignored."""
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = 0
    known_pids = {4321}
    handles: dict = {}

    with patch.object(_windows_process, "_snapshot_processes", return_value=[(4321, 4), (4322, 4321)]), patch.object(
        _windows_process.ctypes, "get_last_error", return_value=_windows_process._ERROR_INVALID_PARAMETER
    ):
        opened = _windows_process._capture_descendant_handles(kernel32, known_pids, handles)

    assert opened == 0
    assert handles == {}


def test_terminate_process_tree_terminates_discovered_descendants() -> None:
    """The native tree walk opens, terminates and waits on every discovered descendant."""
    kernel32 = MagicMock()
    descendant_handle = object()
    kernel32.OpenProcess.return_value = descendant_handle
    kernel32.TerminateProcess.return_value = True
    kernel32.WaitForSingleObject.side_effect = [
        _windows_process._WAIT_TIMEOUT,
        _windows_process._WAIT_OBJECT_0,
    ]
    process = MagicMock(pid=4321)
    process.poll.return_value = None

    snapshots = [[(4321, 4), (4322, 4321)], []]
    with patch.object(_windows_process, "_kernel32", return_value=kernel32), patch.object(
        _windows_process, "_snapshot_processes", side_effect=snapshots
    ):
        _windows_process.terminate_process_tree(process, timeout_secs=1)

    process.kill.assert_called_once_with()
    kernel32.OpenProcess.assert_called_once_with(
        _windows_process._PROCESS_TERMINATE | _windows_process._SYNCHRONIZE, False, 4322
    )
    kernel32.TerminateProcess.assert_called_once_with(descendant_handle, 1)
    kernel32.CloseHandle.assert_called_once_with(descendant_handle)


def test_exiting_descendant_access_denied_is_verified_by_bounded_wait() -> None:
    kernel32 = MagicMock()
    handle = object()
    kernel32.WaitForSingleObject.side_effect = [
        _windows_process._WAIT_TIMEOUT,
        _windows_process._WAIT_TIMEOUT,
        _windows_process._WAIT_OBJECT_0,
    ]
    kernel32.TerminateProcess.return_value = False

    with patch.object(_windows_process.ctypes, "get_last_error", return_value=_windows_process._ERROR_ACCESS_DENIED):
        _windows_process._terminate_handles(kernel32, {4321: handle})
        _windows_process._wait_for_handles(kernel32, {4321: handle}, time.monotonic() + 1)


def test_access_denied_descendant_that_stays_live_still_fails() -> None:
    kernel32 = MagicMock()
    handle = object()
    kernel32.WaitForSingleObject.side_effect = [
        _windows_process._WAIT_TIMEOUT,
        _windows_process._WAIT_TIMEOUT,
        _windows_process._WAIT_TIMEOUT,
    ]
    kernel32.TerminateProcess.return_value = False

    with patch.object(
        _windows_process.ctypes,
        "get_last_error",
        return_value=_windows_process._ERROR_ACCESS_DENIED,
    ), pytest.raises(RuntimeError, match="did not exit"):
        _windows_process._terminate_handles(kernel32, {4321: handle})
        _windows_process._wait_for_handles(kernel32, {4321: handle}, time.monotonic() + 1)
