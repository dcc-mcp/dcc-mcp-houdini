"""Windows process boundary regressions."""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from dcc_mcp_houdini import _windows_process

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows process boundary")


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
