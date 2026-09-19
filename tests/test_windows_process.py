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


def test_child_of_a_rejected_pid_is_rejected_too() -> None:
    """Rejection has to travel down the chain: an orphan's own child is not ours.

    The orphan predates the job root, but its child started after the root and
    after the orphan, so a single-hop check would accept the child and terminate
    a process that has nothing to do with this job.
    """
    kernel32 = _stub_kernel32(openable=[200, 300])
    start_times = {100: 9000, 200: 1000}

    def _start_times(_kernel32, pid):
        return {300: 9500}.get(pid, 1000)

    with patch.object(_windows_process, "_process_start_time", side_effect=_start_times):
        opened, handles = _capture(
            kernel32,
            [(200, 100), (300, 200)],
            {100},
            start_times,
            _windows_process._ERROR_ACCESS_DENIED,
            root_start=9000,
        )

    assert opened == 0
    assert handles == {}
    kernel32.OpenProcess.assert_not_called()


def test_child_of_an_unqueryable_pid_is_rejected_too() -> None:
    """A pid we cannot even query must not become a trusted ancestor."""
    kernel32 = _stub_kernel32(openable=[200, 300])
    start_times = {100: 9000, 200: None}

    def _start_times(_kernel32, pid):
        return {300: 9500}.get(pid)

    with patch.object(_windows_process, "_process_start_time", side_effect=_start_times):
        opened, handles = _capture(
            kernel32,
            [(200, 100), (300, 200)],
            {100},
            start_times,
            _windows_process._ERROR_ACCESS_DENIED,
            root_start=9000,
        )

    assert opened == 0
    assert handles == {}
    kernel32.OpenProcess.assert_not_called()


def test_real_grandchild_of_the_root_is_still_captured() -> None:
    """A genuine two level tree must survive the stricter chain check."""
    kernel32 = _stub_kernel32(openable=[200, 300])
    start_times = {100: 9000}

    with patch.object(_windows_process, "_process_start_time", return_value=9500):
        opened, handles = _capture(
            kernel32,
            [(200, 100), (300, 200)],
            {100},
            start_times,
            _windows_process._ERROR_ACCESS_DENIED,
            root_start=9000,
        )

    assert opened == 2
    assert sorted(handles) == [200, 300]


def test_root_hop_stays_permissive_when_the_root_time_is_unknown() -> None:
    """An unreadable root creation time must not skip every direct child.

    ``subprocess.Popen`` still owns the authoritative root handle, so losing the
    root creation time must not turn a normal cancellation into a timeout.
    """
    kernel32 = _stub_kernel32(openable=[200])

    with patch.object(_windows_process, "_process_start_time", return_value=1000):
        opened, handles = _capture(
            kernel32, [(200, 100)], {100}, {}, _windows_process._ERROR_ACCESS_DENIED, root_start=None
        )

    assert opened == 1
    assert sorted(handles) == [200]


def test_pid_that_exited_before_opening_is_not_a_trusted_ancestor() -> None:
    """A pid whose handle never opened must not join the trusted ancestor set.

    ``ERROR_INVALID_PARAMETER`` means the process exited between the snapshot and
    ``OpenProcess``. The deadline loop reuses the same ``known_pids``, so a pid
    kept here after a failed open can be recycled by the OS and then anchor the
    next snapshot with unrelated processes below it.
    """
    kernel32 = _stub_kernel32()
    known_pids = {100}

    with patch.object(_windows_process, "_process_start_time", return_value=9500):
        opened, handles = _capture(
            kernel32,
            [(200, 100)],
            known_pids,
            {100: 9000},
            _windows_process._ERROR_INVALID_PARAMETER,
            root_start=9000,
        )

    assert opened == 0
    assert handles == {}
    assert known_pids == {100}


def test_exited_pid_does_not_anchor_the_next_snapshot() -> None:
    """The next snapshot must not discover anything below an exited pid.

    First pass: 200 clears the ancestry check but exits before its handle opens.
    Second pass: 300 claims 200 as parent. Because 200 was never trusted, 300 is
    not part of the job tree and must not be opened or terminated.
    """
    kernel32 = _stub_kernel32(openable=[300])
    known_pids = {100}

    with patch.object(_windows_process, "_process_start_time", return_value=9500):
        _capture(
            kernel32,
            [(200, 100)],
            known_pids,
            {100: 9000},
            _windows_process._ERROR_INVALID_PARAMETER,
            root_start=9000,
        )
        opened, handles = _capture(
            kernel32,
            [(300, 200)],
            known_pids,
            {100: 9000},
            _windows_process._ERROR_ACCESS_DENIED,
            root_start=9000,
        )

    assert opened == 0
    assert handles == {}
    assert known_pids == {100}


def test_rejected_pid_never_becomes_a_trusted_ancestor() -> None:
    """The trusted set may only grow with pids that passed the identity check."""
    kernel32 = _stub_kernel32(openable=[200, 300])
    known_pids = {100}

    with patch.object(_windows_process, "_snapshot_processes", return_value=[(200, 100), (300, 200)]), patch.object(
        _windows_process, "_process_start_time", return_value=1000
    ):
        _windows_process._capture_descendant_handles(kernel32, known_pids, {}, 9000, {})

    assert known_pids == {100}


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
