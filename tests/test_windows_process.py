"""Windows process boundary regressions."""

from __future__ import annotations

import sys
import time
from typing import Dict, Iterable, List, Optional, Set, Tuple
from unittest.mock import MagicMock, patch

import pytest

from dcc_mcp_houdini import _windows_process

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows process boundary")


def _stub_kernel32(openable: Iterable[int] = ()) -> MagicMock:
    """Build a kernel32 stub that only hands out handles for *openable* pids."""
    kernel32 = MagicMock()
    handles = {pid: object() for pid in openable}
    kernel32.OpenProcess.side_effect = lambda _access, _inherit, pid: handles.get(pid)
    return kernel32


def _capture(
    kernel32: MagicMock,
    snapshot: List[Tuple[int, int]],
    known_pids: Set[int],
    start_times: Dict[int, Optional[int]],
    error_code: int,
    root_start: Optional[int] = None,
) -> Tuple[int, Dict[int, object]]:
    handles: Dict[int, object] = {}
    with patch.object(_windows_process, "_snapshot_processes", return_value=snapshot), patch.object(
        _windows_process.ctypes, "get_last_error", return_value=error_code
    ):
        opened = _windows_process._capture_descendant_handles(kernel32, known_pids, handles, root_start, start_times)
    return opened, handles


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


def test_recycled_pid_older_than_root_is_skipped() -> None:
    """A pid reuse lookalike that predates the job root is not opened at all."""
    kernel32 = _stub_kernel32(openable=[200])
    start_times = {100: 9000}

    with patch.object(_windows_process, "_process_start_time", return_value=1000):
        opened, handles = _capture(
            kernel32,
            [(200, 100)],
            {100},
            start_times,
            _windows_process._ERROR_ACCESS_DENIED,
            root_start=9000,
        )

    assert opened == 0
    assert handles == {}
    kernel32.OpenProcess.assert_not_called()


def test_recycled_pid_older_than_its_claimed_parent_is_skipped() -> None:
    """An orphan can predate a mid-tree pid it only appears to be a child of."""
    kernel32 = _stub_kernel32(openable=[300])
    start_times = {200: 9000}

    with patch.object(_windows_process, "_process_start_time", return_value=5000):
        opened, handles = _capture(
            kernel32, [(300, 200)], {100, 200}, start_times, _windows_process._ERROR_ACCESS_DENIED
        )

    assert opened == 0
    assert handles == {}
    kernel32.OpenProcess.assert_not_called()


def test_process_that_hides_from_query_limited_information_is_skipped() -> None:
    """Another security context or a protected process cannot be one we spawned."""
    kernel32 = _stub_kernel32(openable=[200])

    with patch.object(_windows_process, "_process_start_time", return_value=None):
        opened, handles = _capture(kernel32, [(200, 100)], {100}, {}, _windows_process._ERROR_ACCESS_DENIED)

    assert opened == 0
    assert handles == {}
    kernel32.OpenProcess.assert_not_called()


def test_real_descendant_access_denied_still_fails_closed() -> None:
    """A genuine descendant that refuses PROCESS_TERMINATE keeps raising."""
    kernel32 = _stub_kernel32()
    start_times = {100: 9000}

    with patch.object(_windows_process, "_process_start_time", return_value=9500), pytest.raises(
        RuntimeError, match="Failed to open an owned background process"
    ):
        _capture(kernel32, [(200, 100)], {100}, start_times, _windows_process._ERROR_ACCESS_DENIED, root_start=9000)


def test_invalid_parameter_is_skipped() -> None:
    """WinError 87 (process gone between snapshot and open) stays non-fatal."""
    kernel32 = _stub_kernel32()
    start_times = {100: 9000}

    with patch.object(_windows_process, "_process_start_time", return_value=9500):
        opened, handles = _capture(
            kernel32,
            [(200, 100)],
            {100},
            start_times,
            _windows_process._ERROR_INVALID_PARAMETER,
            root_start=9000,
        )

    assert opened == 0
    assert handles == {}


def test_real_descendant_handle_is_captured() -> None:
    kernel32 = _stub_kernel32(openable=[200])
    start_times = {100: 9000}

    with patch.object(_windows_process, "_process_start_time", return_value=9500):
        opened, handles = _capture(
            kernel32,
            [(200, 100)],
            {100},
            start_times,
            _windows_process._ERROR_ACCESS_DENIED,
            root_start=9000,
        )

    assert opened == 1
    assert sorted(handles) == [200]


def test_process_start_time_packs_filetime() -> None:
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = object()

    def _fill_times(_handle, creation, _exit, _kernel, _user):
        creation.dwHighDateTime = 1
        creation.dwLowDateTime = 2
        return True

    kernel32.GetProcessTimes.side_effect = _fill_times

    with patch.object(_windows_process.ctypes, "byref", lambda obj: obj):
        start_time = _windows_process._process_start_time(kernel32, 4242)

    assert start_time == (1 << 32) | 2
    kernel32.OpenProcess.assert_called_once_with(_windows_process._PROCESS_QUERY_LIMITED_INFORMATION, False, 4242)
    kernel32.CloseHandle.assert_called_once()


def test_process_start_time_is_none_when_the_process_cannot_be_queried() -> None:
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = None

    assert _windows_process._process_start_time(kernel32, 4242) is None
    kernel32.CloseHandle.assert_not_called()


def test_terminate_process_tree_threads_the_root_start_time() -> None:
    process = MagicMock(pid=100)
    process.poll.return_value = None
    kernel32 = _stub_kernel32(openable=[200])

    with patch.object(_windows_process, "_kernel32", return_value=kernel32), patch.object(
        _windows_process, "_snapshot_processes", return_value=[(200, 100)]
    ), patch.object(_windows_process, "_process_start_time", return_value=9000), patch.object(
        _windows_process, "_terminate_handles"
    ) as terminate, patch.object(_windows_process, "_wait_for_handles"):
        _windows_process.terminate_process_tree(process, timeout_secs=5.0)

    process.kill.assert_called_once()
    assert set(terminate.call_args[0][1]) == {200}
