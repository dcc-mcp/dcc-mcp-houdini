"""Windows-native process-tree termination for adapter-owned workers."""

from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes
from typing import Any, Dict, Iterable, List, Set, Tuple

_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_TERMINATE = 0x0001
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_ERROR_ACCESS_DENIED = 5
_ERROR_NO_MORE_FILES = 18
_ERROR_INVALID_PARAMETER = 87
_MAX_PATH = 260


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * _MAX_PATH),
    ]


def _kernel32() -> Any:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _raise_windows_error(message: str, error_code: int) -> None:
    error = ctypes.WinError(error_code)
    raise RuntimeError("{}: {}".format(message, error)) from error


def _snapshot_processes(kernel32: Any) -> List[Tuple[int, int]]:
    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if not snapshot or snapshot == invalid_handle:
        _raise_windows_error("Failed to snapshot the background process tree", ctypes.get_last_error())
    entries: List[Tuple[int, int]] = []
    try:
        entry = _ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            error_code = ctypes.get_last_error()
            if error_code == _ERROR_NO_MORE_FILES:
                return entries
            _raise_windows_error("Failed to inspect the background process tree", error_code)
        while True:
            entries.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                error_code = ctypes.get_last_error()
                if error_code != _ERROR_NO_MORE_FILES:
                    _raise_windows_error("Failed to inspect the background process tree", error_code)
                return entries
    finally:
        kernel32.CloseHandle(snapshot)


def _find_descendants(entries: Iterable[Tuple[int, int]], ancestor_pids: Set[int]) -> Set[int]:
    descendants: Set[int] = set()
    remaining = list(entries)
    while True:
        discovered = {
            pid
            for pid, parent_pid in remaining
            if pid not in ancestor_pids and pid not in descendants and parent_pid in ancestor_pids.union(descendants)
        }
        if not discovered:
            return descendants
        descendants.update(discovered)


def _capture_descendant_handles(
    kernel32: Any,
    known_pids: Set[int],
    handles: Dict[int, Any],
) -> int:
    descendants = _find_descendants(_snapshot_processes(kernel32), known_pids)
    new_pids = descendants.difference(known_pids)
    known_pids.update(descendants)
    opened = 0
    for pid in sorted(new_pids):
        handle = kernel32.OpenProcess(_PROCESS_TERMINATE | _SYNCHRONIZE, False, pid)
        if not handle:
            error_code = ctypes.get_last_error()
            if error_code == _ERROR_INVALID_PARAMETER:
                continue
            _raise_windows_error("Failed to open an owned background process", error_code)
        handles[pid] = handle
        opened += 1
    return opened


def _terminate_handles(kernel32: Any, handles: Dict[int, Any]) -> None:
    for handle in handles.values():
        if kernel32.WaitForSingleObject(handle, 0) == _WAIT_OBJECT_0:
            continue
        if kernel32.TerminateProcess(handle, 1):
            continue
        error_code = ctypes.get_last_error()
        if kernel32.WaitForSingleObject(handle, 0) == _WAIT_OBJECT_0:
            continue
        if error_code == _ERROR_ACCESS_DENIED:
            _raise_windows_error("Access was denied while terminating an owned background process", error_code)
        _raise_windows_error("Failed to terminate an owned background process", error_code)


def _remaining_millis(deadline: float) -> int:
    remaining = max(0.0, deadline - time.monotonic())
    return min(int(remaining * 1000), 0xFFFFFFFE)


def _wait_for_handles(kernel32: Any, handles: Dict[int, Any], deadline: float) -> None:
    for handle in handles.values():
        result = kernel32.WaitForSingleObject(handle, _remaining_millis(deadline))
        if result == _WAIT_OBJECT_0:
            continue
        if result == _WAIT_TIMEOUT:
            raise RuntimeError("Background process tree did not exit")
        _raise_windows_error("Failed while waiting for the background process tree", ctypes.get_last_error())


def terminate_process_tree(process: Any, timeout_secs: float) -> None:
    """Terminate an owned Popen process and every descendant without spawning a helper."""
    if process.poll() is not None:
        return
    kernel32 = _kernel32()
    root_pid = int(process.pid)
    known_pids = {root_pid}
    handles: Dict[int, Any] = {}
    deadline = time.monotonic() + timeout_secs
    try:
        _capture_descendant_handles(kernel32, known_pids, handles)
        try:
            process.kill()
        except OSError:
            if process.poll() is None:
                raise
        _terminate_handles(kernel32, handles)
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Background process tree did not exit") from exc
        _wait_for_handles(kernel32, handles, deadline)

        while _capture_descendant_handles(kernel32, known_pids, handles):
            _terminate_handles(kernel32, handles)
            _wait_for_handles(kernel32, handles, deadline)
            if time.monotonic() >= deadline:
                raise RuntimeError("Background process tree did not exit")
    finally:
        for handle in handles.values():
            kernel32.CloseHandle(handle)
