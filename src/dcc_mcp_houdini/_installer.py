"""Houdini-owned Install SOP lifecycle built on public Core primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import unquote, urlsplit

import dcc_mcp_core
from dcc_mcp_core import (
    inspect_install_root,
    query_runtime_state,
    safe_remove_tree,
    safe_replace_tree,
    wait_for_sidecar_ready,
)
from dcc_mcp_core.deployment import (
    INSTALL_EXIT_INSTALL,
    INSTALL_EXIT_OK,
    INSTALL_EXIT_PREFLIGHT,
    INSTALL_EXIT_REQUIRES_RESTART,
    INSTALL_EXIT_VERIFY,
    INSTALL_SOP_SCHEMA_VERSION,
)

from dcc_mcp_houdini.__version__ import __version__

DCC_TYPE = "houdini"
COMMAND = "dcc-mcp-houdini"
MIN_CORE_VERSION = "0.20.14"
MIN_HOUDINI_VERSION = (18, 5, 0)
LIFECYCLE_COMMANDS = frozenset(("install", "status", "verify", "uninstall", "upgrade"))

_PYTHON_ENV = "DCC_MCP_INSTALL_PYTHON"
_PACKAGES_ENV = "DCC_MCP_HOUDINI_PACKAGES_DIR"
_INSTALL_DIR = "dcc-mcp-houdini"
_PACKAGE_FILE = "dcc_mcp_houdini.json"
_READINESS_TOOL = "houdini_scripting__get_session_info"
_VERSION_COMPONENT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,5})$")
_HOST_VERSION_RE = re.compile(
    r"^Houdini[ _-]?(?P<version>(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5}))$",
    re.IGNORECASE,
)
_MAX_VERSION_LENGTH = 32
_MAX_PROBE_OUTPUT_BYTES = 16 * 1024
_MAX_PUBLIC_ERROR_LENGTH = 512
_MAX_TRANSACTION_SNAPSHOT_BYTES = 8 * 1024 * 1024
_MAX_RECEIPT_BYTES = 1024 * 1024
_HOST_EXECUTABLES = frozenset(
    (
        "houdini",
        "houdini.exe",
        "houdinifx",
        "houdinifx.exe",
        "hindie",
        "hindie.exe",
    )
)
_HYTHON_EXECUTABLES = frozenset(("hython", "hython.exe"))


@dataclass(frozen=True)
class InstallContext:
    host_path: Path
    host_version: str
    host_version_source: str
    python_path: Path
    python_source: str
    python_version: str
    core_version: str
    hou_module_path: Path
    adapter_module_path: Path
    core_module_path: Path
    profile: Path
    packages_dir: Path
    package_file: Path
    install_root: Path
    receipt_path: Path
    bootstrap_log_dir: Path
    state: str
    receipt: Optional[dict[str, Any]]


@dataclass(frozen=True)
class LifecycleOutcome:
    result: dict[str, Any]
    exit_code: int


class LifecycleFailure(RuntimeError):
    """Classified public lifecycle failure."""

    def __init__(self, stage: str, message: str, exit_code: int = INSTALL_EXIT_PREFLIGHT) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code


def _bounded_text(value: object, fallback: str = "invalid value") -> str:
    text = str(value).strip()
    return text if 0 < len(text) <= _MAX_PUBLIC_ERROR_LENGTH else fallback


def _version_tuple(value: object, *, components: int = 3) -> Optional[tuple[int, ...]]:
    """Parse one bounded canonical numeric final version before integer conversion."""
    if not isinstance(value, str) or not 0 < len(value) <= _MAX_VERSION_LENGTH:
        return None
    parts = value.split(".")
    if len(parts) != components or any(_VERSION_COMPONENT_RE.fullmatch(part) is None for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _require_nonempty_file(path: Path, stage: str, description: str) -> Path:
    try:
        if not path.is_file() or _is_link_or_junction(path) or path.stat().st_size <= 0:
            raise LifecycleFailure(stage, "{} is missing, empty, or an unsupported link.".format(description))
    except OSError as exc:
        raise LifecycleFailure(stage, "{} could not be inspected.".format(description)) from exc
    return path.resolve()


def _run_bounded_command(command: Sequence[str], timeout: float = 20.0) -> dict[str, Any]:
    """Run a probe without retaining unbounded child output in memory."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with tempfile.TemporaryFile(mode="w+b") as stdout_file:
        with tempfile.TemporaryFile(mode="w+b") as stderr_file:
            try:
                process = subprocess.Popen(
                    list(command),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    creationflags=creationflags,
                )
            except OSError as exc:
                return {"success": False, "reason": "launch failed: {}".format(exc.__class__.__name__)}
            try:
                process.wait(timeout=max(0.1, min(float(timeout), 30.0)))
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    pass
                return {"success": False, "reason": "probe timed out"}
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(_MAX_PROBE_OUTPUT_BYTES + 1)
            stderr = stderr_file.read(_MAX_PROBE_OUTPUT_BYTES + 1)
    return {
        "success": process.returncode == 0,
        "returncode": int(process.returncode or 0),
        "stdout": stdout[:_MAX_PROBE_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        "stderr": stderr[:_MAX_PROBE_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        "truncated": len(stdout) > _MAX_PROBE_OUTPUT_BYTES or len(stderr) > _MAX_PROBE_OUTPUT_BYTES,
    }


def _process_executable_path(pid: int) -> Optional[Path]:
    """Return the executable for one live PID without following registry claims."""
    if pid <= 0:
        return None
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32_768)
            length = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                return None
            return Path(buffer.value).resolve()
        finally:
            kernel32.CloseHandle(handle)
    if sys.platform == "darwin":
        import ctypes

        buffer = ctypes.create_string_buffer(4096)
        try:
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
            length = int(libproc.proc_pidpath(int(pid), buffer, len(buffer)))
        except (OSError, AttributeError):
            return None
        if length <= 0:
            return None
        return Path(buffer.value.decode("utf-8", errors="strict")).resolve()
    try:
        return Path("/proc/{}/exe".format(pid)).resolve(strict=True)
    except OSError:
        return None


def _process_start_identity(pid: int) -> Optional[str]:
    """Return a stable start identity so a reused PID cannot satisfy readiness."""
    if pid <= 0:
        return None
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
            return "windows-filetime:{}".format(value)
        finally:
            kernel32.CloseHandle(handle)
    if sys.platform == "darwin":
        completed = _run_bounded_command(["ps", "-p", str(pid), "-o", "lstart="], timeout=3.0)
        value = str(completed.get("stdout") or "").strip()
        return "darwin-lstart:{}".format(value) if completed.get("success") and value else None
    try:
        stat = Path("/proc/{}/stat".format(pid)).read_text(encoding="utf-8")
        closing = stat.rfind(") ")
        if closing < 0:
            return None
        start_ticks = stat[closing + 2 :].split()[19]
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except (IndexError, OSError, ValueError):
        return None
    return "linux:{}:{}".format(boot_id, start_ticks)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file() or _is_link_or_junction(path) or not 0 < path.stat().st_size <= _MAX_RECEIPT_BYTES:
            raise ValueError("receipt file is missing, linked, empty, or unbounded")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LifecycleFailure("receipt", "Install receipt is unreadable: {}".format(exc)) from exc
    if not isinstance(value, dict):
        raise LifecycleFailure("receipt", "Install receipt root must be an object.")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    temporary.write_text(value, encoding="utf-8")
    os.replace(str(temporary), str(path))


def _host_candidates(environ: Mapping[str, str]) -> Sequence[Path]:
    candidates = set()
    if os.name == "nt":
        for key in ("ProgramFiles", "ProgramW6432"):
            root = environ.get(key, "").strip()
            if root:
                candidates.update(Path(root).glob("Side Effects Software/Houdini*/bin/houdini.exe"))
    elif sys.platform == "darwin":
        candidates.update(Path("/Applications/Houdini").glob("Houdini*.app/Contents/MacOS/houdini"))
    else:
        candidates.update(Path("/opt").glob("hfs*/bin/houdini"))
        discovered = shutil.which("houdini")
        if discovered:
            candidates.add(Path(discovered))
    return tuple(sorted((path.resolve() for path in candidates if path.is_file()), key=str))


def _resolve_host(value: Optional[str], environ: Mapping[str, str]) -> Path:
    if value:
        candidate = Path(value).expanduser().resolve()
        if candidate.is_dir():
            names = (
                "houdini.exe",
                "houdini",
                "houdinifx.exe",
                "houdinifx",
                "hindie.exe",
                "hindie",
            )
            nested = [candidate / "bin" / name for name in names]
            nested.extend(candidate / name for name in names)
            matches = [path for path in nested if path.is_file()]
            if len(matches) == 1:
                candidate = matches[0]
            elif matches:
                candidate = next((path for path in matches if path.name.lower().startswith("houdini")), matches[0])
        if candidate.name.lower() not in _HOST_EXECUTABLES:
            raise LifecycleFailure("host", "--dcc-path must select an interactive Houdini executable exactly.")
        if candidate.is_file():
            return _require_nonempty_file(candidate, "host", "Selected Houdini executable")
        raise LifecycleFailure("host", "Houdini executable does not exist: {}".format(candidate))
    candidates = _host_candidates(environ)
    if len(candidates) == 1:
        return _require_nonempty_file(candidates[0], "host", "Discovered Houdini executable")
    if not candidates:
        raise LifecycleFailure("host", "Houdini was not found; pass its exact executable with --dcc-path.")
    raise LifecycleFailure("host", "Multiple Houdini installations were found; select one with --dcc-path.")


def _host_version(path: Path) -> tuple[str, str]:
    for text in (path.name, *(parent.name for parent in tuple(path.parents)[:8])):
        match = _HOST_VERSION_RE.fullmatch(text)
        if match:
            return match.group("version"), "path"
    return "", "unavailable"


def _host_root(path: Path) -> Path:
    for parent in tuple(path.parents)[:8]:
        if _HOST_VERSION_RE.fullmatch(parent.name):
            return parent
    if path.parent.name.lower() == "bin":
        return path.parent.parent
    if path.parent.name.lower() == "macos" and path.parent.parent.name.lower() == "contents":
        return path.parent.parent
    return path.parent


def _resolve_python(value: Optional[str], host: Path, environ: Mapping[str, str]) -> tuple[Path, str]:
    configured = value or environ.get(_PYTHON_ENV)
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.name.lower() not in _HYTHON_EXECUTABLES:
            raise LifecycleFailure("python", "Target interpreter must be Houdini's exact hython executable.")
        path = _require_nonempty_file(path, "python", "Selected Hython interpreter")
        if not _same_path(_host_root(path), _host_root(host)):
            raise LifecycleFailure("python", "Selected Hython belongs to a different Houdini installation.")
        return path, "--python" if value else _PYTHON_ENV
    executable = "hython.exe" if os.name == "nt" else "hython"
    candidate = _host_root(host) / "bin" / executable
    if candidate.is_file():
        return _require_nonempty_file(candidate, "python", "Houdini Hython interpreter"), "host_install"
    raise LifecycleFailure(
        "python",
        "Houdini's hython interpreter was not found; pass its exact executable with --python.",
    )


def _query_python(path: Path, host: Path) -> dict[str, str]:
    script = r"""
try:
    import importlib.metadata as md
except ImportError:
    import importlib_metadata as md
import json
import pathlib
import sys
import hou
import dcc_mcp_core
import dcc_mcp_houdini as adapter

ad = md.distribution("dcc-mcp-houdini")
co = md.distribution("dcc-mcp-core")
af = {str(pathlib.Path(ad.locate_file(item)).resolve()): str(item) for item in tuple(ad.files or ())}
cf = {str(pathlib.Path(co.locate_file(item)).resolve()): str(item) for item in tuple(co.files or ())}
au = ad.read_text("direct_url.json")
cu = co.read_text("direct_url.json")
ap = str(pathlib.Path(adapter.__file__).resolve())
cp = str(pathlib.Path(dcc_mcp_core.__file__).resolve())
print(json.dumps({
    "python_version": ".".join(map(str, sys.version_info[:3])),
    "core_version": dcc_mcp_core.__version__,
    "core_dist_version": co.version,
    "adapter_version": adapter.__version__,
    "adapter_dist_version": ad.version,
    "host_version": hou.applicationVersionString(),
    "executable": sys.executable,
    "hou_file": getattr(hou, "__file__", None),
    "adapter_file": ap,
    "core_file": cp,
    "adapter_dist_root": str(pathlib.Path(ad.locate_file("")).resolve()),
    "core_dist_root": str(pathlib.Path(co.locate_file("")).resolve()),
    "adapter_record": af.get(ap),
    "core_record": cf.get(cp),
    "adapter_direct_url": json.loads(au) if au else None,
    "core_direct_url": json.loads(cu) if cu else None,
}))
""".strip()
    completed = _run_bounded_command([str(path), "-c", script], timeout=20.0)
    if not completed.get("success") or completed.get("truncated"):
        details = str(completed.get("stderr") or completed.get("stdout") or "").strip().splitlines()
        detail = details[-1] if details else str(completed.get("reason") or "probe failed")
        raise LifecycleFailure("python", "Target interpreter import check failed: {}".format(detail))
    try:
        result = json.loads(str(completed.get("stdout") or "").strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise LifecycleFailure("python", "Target interpreter returned invalid metadata.") from exc
    if not isinstance(result, dict):
        raise LifecycleFailure("python", "Target interpreter returned invalid metadata.")
    reported_python = Path(str(result.get("executable") or ""))
    if not reported_python.is_file() or not _same_path(reported_python, path):
        raise LifecycleFailure("python", "Target interpreter identity does not match selected Hython.")
    adapter_version = _version_tuple(result.get("adapter_version"))
    adapter_dist_version = _version_tuple(result.get("adapter_dist_version"))
    if adapter_version is None or adapter_dist_version is None or result.get("adapter_version") != __version__:
        raise LifecycleFailure(
            "python",
            "Target interpreter adapter version does not match this installer.",
        )
    if result.get("adapter_version") != result.get("adapter_dist_version"):
        raise LifecycleFailure("python", "Imported adapter version does not match its installed distribution.")
    core_version = _version_tuple(result.get("core_version"))
    core_dist_version = _version_tuple(result.get("core_dist_version"))
    core_floor = _version_tuple(MIN_CORE_VERSION)
    if core_version is None or core_dist_version is None or core_floor is None:
        raise LifecycleFailure("core_version", "dcc-mcp-core returned a noncanonical final version.")
    if result.get("core_version") != result.get("core_dist_version"):
        raise LifecycleFailure("python", "Imported Core version does not match its installed distribution.")
    if core_version < core_floor:
        raise LifecycleFailure("core_version", "dcc-mcp-core>={} is required.".format(MIN_CORE_VERSION))
    python_version = _version_tuple(result.get("python_version"))
    if python_version is None or python_version < (3, 7, 0):
        raise LifecycleFailure("python_version", "Houdini Python 3.7 or newer is required.")
    hou_file = _require_nonempty_file(Path(str(result.get("hou_file") or "")), "python", "Imported HOM module")
    adapter_file = _require_nonempty_file(
        Path(str(result.get("adapter_file") or "")), "python", "Imported Houdini adapter module"
    )
    core_file = _require_nonempty_file(Path(str(result.get("core_file") or "")), "python", "Imported Core module")
    _require_genuine_hom_origin(hou_file, host, python_version)
    _require_distribution_origin(
        adapter_file,
        result.get("adapter_dist_root"),
        result.get("adapter_record"),
        result.get("adapter_direct_url"),
        distribution="adapter",
        package="dcc_mcp_houdini",
    )
    _require_distribution_origin(
        core_file,
        result.get("core_dist_root"),
        result.get("core_record"),
        result.get("core_direct_url"),
        distribution="Core",
        package="dcc_mcp_core",
    )
    return {str(key): "" if value is None else str(value) for key, value in result.items()}


def _editable_distribution_root(value: object) -> Optional[Path]:
    if not isinstance(value, dict) or not isinstance(value.get("dir_info"), dict):
        return None
    url = value.get("url")
    if value["dir_info"].get("editable") is not True or not isinstance(url, str) or not 0 < len(url) <= 2048:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "file" or parsed.query or parsed.fragment:
        return None
    raw_path = unquote(parsed.path)
    if re.fullmatch(r"/[A-Za-z]:/.*", raw_path):
        raw_path = raw_path[1:]
    try:
        root = Path(raw_path).resolve()
    except (OSError, ValueError):
        return None
    return root if root.is_dir() and not _is_link_or_junction(root) else None


def _require_distribution_origin(
    module_file: Path,
    root_value: object,
    record_value: object,
    direct_url: object,
    *,
    distribution: str,
    package: str,
) -> None:
    root_text = str(root_value or "")
    root = Path(root_text)
    if (
        not root_text
        or not root.is_dir()
        or _is_link_or_junction(root)
        or module_file.name != "__init__.py"
        or module_file.parent.name != package
    ):
        raise LifecycleFailure(
            "python", "Imported {} module is shadowed outside its distribution.".format(distribution)
        )
    if isinstance(record_value, str) and 0 < len(record_value) <= 1024:
        record_path = Path(record_value)
        if record_path.is_absolute() or ".." in record_path.parts:
            raise LifecycleFailure("python", "Imported {} module has invalid RECORD ownership.".format(distribution))
        if not _same_path(root / record_path, module_file) or not _path_within(module_file, root):
            raise LifecycleFailure("python", "Imported {} module is not owned by its RECORD.".format(distribution))
        return
    editable = _editable_distribution_root(direct_url)
    candidates = (
        () if editable is None else (editable / "src" / package / "__init__.py", editable / package / "__init__.py")
    )
    if not any(_same_path(module_file, candidate) for candidate in candidates):
        raise LifecycleFailure(
            "python", "Imported {} module has no validated RECORD or editable ownership.".format(distribution)
        )


def _require_genuine_hom_origin(hou_file: Path, host: Path, python_version: tuple[int, ...]) -> None:
    root = _host_root(host)
    library = root / "houdini" / "python{}.{}libs".format(python_version[0], python_version[1])
    if hou_file.parent.resolve() != library.resolve() or hou_file.name.lower() not in ("hou.py", "hou.pyd", "hou.so"):
        raise LifecycleFailure("python", "Imported HOM module is not from the selected Hython library.")


def _profile_paths(host_version: str, environ: Mapping[str, str]) -> tuple[Path, Path]:
    override = environ.get(_PACKAGES_ENV, "").strip()
    if override:
        packages = Path(override).expanduser().resolve()
        return packages.parent, packages
    parsed = _version_tuple(host_version)
    if parsed is None:
        raise LifecycleFailure("host_version", "The Houdini profile version could not be resolved.")
    short_version = ".".join(str(part) for part in parsed[:2])
    home = Path.home()
    if os.name == "nt":
        profile = home / "Documents" / "houdini{}".format(short_version)
    else:
        profile = home / "houdini{}".format(short_version)
    return profile.resolve(), (profile / "packages").resolve()


def _package_payload(install_root: Path) -> str:
    root = install_root.as_posix()
    return (
        json.dumps(
            {
                "env": [
                    {"DCC_MCP_HOUDINI_ROOT": root},
                    {"HOUDINI_PATH": root + ";&"},
                ]
            },
            indent=2,
        )
        + "\n"
    )


def _bootstrap_source(log_dir: Path) -> str:
    return '''"""DCC-MCP Houdini startup owned by the install receipt."""
from __future__ import annotations

import os


def bootstrap_and_start():
    from dcc_mcp_core import capture_bootstrap_errors

    with capture_bootstrap_errors(
        "houdini",
        adapter_version={adapter_version!r},
        min_core_version={min_core!r},
        phase="startup",
        log_dir={log_dir!r},
    ):
        if os.environ.get("DCC_MCP_BACKGROUND_RENDER") == "1":
            return None
        if os.environ.get("DCC_MCP_HOUDINI_AUTOSTART", "1").strip().lower() in {{"0", "false", "no", "off"}}:
            return None
        import hou
        if not hou.isUIAvailable():
            print("dcc-mcp-houdini: headless hook skipped; run hython -m dcc_mcp_houdini")
            return None
        import dcc_mcp_houdini
        gateway = os.environ.get("DCC_MCP_GATEWAY_PORT")
        return dcc_mcp_houdini.start_server(
            gateway_port=int(gateway) if gateway and gateway.isdigit() else None,
            registry_dir=os.environ.get("DCC_MCP_REGISTRY_DIR") or None,
            wait_ready=False,
        )
'''.format(adapter_version=__version__, min_core=MIN_CORE_VERSION, log_dir=str(log_dir))


def _hook_source(log_dir: Path) -> str:
    return '''"""Autostart DCC-MCP after Houdini initializes or loads a scene."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path


try:
    from dcc_mcp_core import capture_bootstrap_errors
    with capture_bootstrap_errors(
        "houdini",
        adapter_version={adapter_version!r},
        min_core_version={min_core!r},
        phase="startup-hook",
        log_dir={log_dir!r},
    ):
        root = os.environ.get("DCC_MCP_HOUDINI_ROOT")
        script = globals().get("__file__")
        path = Path(root) / "scripts/dcc_mcp_houdini_bootstrap.py" if root else Path(script).with_name("dcc_mcp_houdini_bootstrap.py")
        spec = importlib.util.spec_from_file_location("dcc_mcp_houdini_bootstrap", str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load {{}}".format(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        server = module.bootstrap_and_start()
        if server is not None:
            print("dcc-mcp-houdini MCP server started: {{}}".format(server.mcp_url))
except Exception as exc:
    print("dcc-mcp-houdini autostart failed: {{}}".format(exc))
'''.format(adapter_version=__version__, min_core=MIN_CORE_VERSION, log_dir=str(log_dir))


def _expected_sources(ctx: InstallContext) -> dict[str, str]:
    return {
        "scripts/dcc_mcp_houdini_bootstrap.py": _bootstrap_source(ctx.bootstrap_log_dir),
        "scripts/123.py": _hook_source(ctx.bootstrap_log_dir),
        "scripts/456.py": _hook_source(ctx.bootstrap_log_dir),
    }


def _file_record(path: Path, *, relative_to: Optional[Path] = None) -> dict[str, Any]:
    resolved = _require_nonempty_file(path, "receipt", "Managed Houdini file")
    record_path = resolved.relative_to(relative_to.resolve()).as_posix() if relative_to else str(resolved)
    return {"path": record_path, "sha256": _hash_file(resolved), "size": resolved.stat().st_size}


def _owned_root_manifest(root: Path) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    if not root.is_dir() or _is_link_or_junction(root):
        raise LifecycleFailure("receipt", "Managed Houdini install root is missing or linked.", INSTALL_EXIT_INSTALL)
    directories = []
    files = []
    links = []
    for current, dirnames, filenames in os.walk(str(root), topdown=True, followlinks=False):
        current_path = Path(current)
        traversable_directories = []
        for name in sorted(dirnames):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if _is_link_or_junction(path):
                links.append(relative)
            else:
                directories.append(relative)
                traversable_directories.append(name)
        dirnames[:] = traversable_directories
        for name in sorted(filenames):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if _is_link_or_junction(path):
                links.append(relative)
            else:
                files.append(_file_record(path, relative_to=root))
    return sorted(directories), sorted(files, key=lambda item: item["path"]), sorted(links)


def _valid_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and not path.drive and ".." not in path.parts and path.as_posix() == value


def _validate_owned_install(
    install_root: Path,
    package_file: Path,
    receipt_path: Path,
    receipt: Mapping[str, Any],
) -> None:
    required = {
        "dcc_type": DCC_TYPE,
        "install_root": str(install_root),
        "package_file": str(package_file),
    }
    if any(str(receipt.get(key, "")) != expected for key, expected in required.items()):
        raise LifecycleFailure(
            "receipt", "Install receipt does not own the selected Houdini profile.", INSTALL_EXIT_INSTALL
        )
    host = receipt.get("host") if isinstance(receipt.get("host"), dict) else {}
    python = receipt.get("python") if isinstance(receipt.get("python"), dict) else {}
    for version in (
        receipt.get("adapter_version"),
        receipt.get("core_version"),
        host.get("version"),
        python.get("version"),
    ):
        if _version_tuple(version) is None:
            raise LifecycleFailure("receipt", "Install receipt contains a noncanonical version.", INSTALL_EXIT_INSTALL)
    if not receipt_path.is_file() or _is_link_or_junction(receipt_path):
        raise LifecycleFailure("receipt", "Install receipt is missing or linked.", INSTALL_EXIT_INSTALL)
    ownership = receipt.get("ownership")
    if not isinstance(ownership, dict):
        raise LifecycleFailure("receipt", "Install receipt ownership manifest is missing.", INSTALL_EXIT_INSTALL)
    expected_directories = ownership.get("directories")
    expected_files = ownership.get("files")
    expected_links = ownership.get("links")
    expected_package = ownership.get("package_file")
    if not isinstance(expected_directories, list) or not all(
        _valid_relative_path(value) for value in expected_directories
    ):
        raise LifecycleFailure("receipt", "Install receipt directory ownership is invalid.", INSTALL_EXIT_INSTALL)
    if not isinstance(expected_links, list) or expected_links:
        raise LifecycleFailure("receipt", "Install receipt link ownership is invalid.", INSTALL_EXIT_INSTALL)
    if not isinstance(expected_files, list) or not expected_files:
        raise LifecycleFailure("receipt", "Install receipt file ownership is invalid.", INSTALL_EXIT_INSTALL)
    for record in expected_files:
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "sha256", "size"}
            or not _valid_relative_path(record.get("path"))
            or re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))) is None
            or not isinstance(record.get("size"), int)
            or record["size"] <= 0
        ):
            raise LifecycleFailure("receipt", "Install receipt file ownership is invalid.", INSTALL_EXIT_INSTALL)
    if (
        not isinstance(expected_package, dict)
        or set(expected_package) != {"path", "sha256", "size"}
        or str(expected_package.get("path")) != str(package_file)
    ):
        raise LifecycleFailure("receipt", "Install receipt package ownership is invalid.", INSTALL_EXIT_INSTALL)
    actual_directories, actual_files, actual_links = _owned_root_manifest(install_root)
    if (
        actual_directories != sorted(expected_directories)
        or actual_files != sorted(expected_files, key=lambda item: item["path"])
        or actual_links != expected_links
        or _file_record(package_file) != expected_package
    ):
        raise LifecycleFailure(
            "receipt",
            "Managed Houdini files, directories, links, or package registration differ from the receipt.",
            INSTALL_EXIT_INSTALL,
        )


def _state(
    install_root: Path,
    package_file: Path,
    receipt_path: Path,
    expected_package: str,
) -> tuple[str, Optional[dict[str, Any]]]:
    artifacts = install_root.exists() or package_file.exists()
    if not receipt_path.is_file():
        return ("partial", None) if artifacts else ("fresh", None)
    try:
        receipt = _load_json(receipt_path)
    except LifecycleFailure:
        return "partial", None
    if receipt.get("schema_version") != 1 or receipt.get("dcc_type") != DCC_TYPE:
        return "partial", receipt
    if Path(str(receipt.get("install_root", ""))).resolve() != install_root.resolve():
        return "partial", receipt
    if Path(str(receipt.get("package_file", ""))).resolve() != package_file.resolve():
        return "partial", receipt
    try:
        intact = package_file.is_file() and package_file.read_text(encoding="utf-8") == expected_package
    except (OSError, UnicodeError):
        intact = False
    try:
        _validate_owned_install(install_root, package_file, receipt_path, receipt)
    except LifecycleFailure:
        intact = False
    if receipt.get("adapter_version") != __version__:
        return ("upgrade" if intact else "repair"), receipt
    return ("current" if intact else "repair"), receipt


def _resolve_context(
    dcc_path: Optional[str],
    python_path: Optional[str],
    environ: Mapping[str, str],
) -> InstallContext:
    host = _resolve_host(dcc_path, environ)
    host_version, host_source = _host_version(host)
    interpreter, python_source = _resolve_python(python_path, host, environ)
    python = _query_python(interpreter, host)
    embedded_version = python.get("host_version", "")
    if embedded_version:
        parsed_host = _version_tuple(host_version) if host_version else None
        parsed_embedded = _version_tuple(embedded_version)
        if parsed_embedded is None:
            raise LifecycleFailure("host_version", "HOM returned a noncanonical Houdini version.")
        if parsed_host is not None and parsed_host != parsed_embedded:
            raise LifecycleFailure(
                "host_version",
                "Selected host {} does not match hython {}.".format(host_version, embedded_version),
            )
        host_version, host_source = embedded_version, "hython"
    parsed_version = _version_tuple(host_version)
    if parsed_version is None or parsed_version < MIN_HOUDINI_VERSION:
        raise LifecycleFailure("host_version", "Houdini 18.5 or newer is required and must be verifiable.")
    profile, packages = _profile_paths(host_version, environ)
    install_root = profile / _INSTALL_DIR
    package_file = packages / _PACKAGE_FILE
    receipt_path = profile / ".dcc-mcp" / "receipts" / "houdini.json"
    expected_package = _package_payload(install_root)
    state, receipt = _state(install_root, package_file, receipt_path, expected_package)
    return InstallContext(
        host_path=host,
        host_version=host_version,
        host_version_source=host_source,
        python_path=interpreter,
        python_source=python_source,
        python_version=python["python_version"],
        core_version=python["core_version"],
        hou_module_path=Path(python["hou_file"]).resolve(),
        adapter_module_path=Path(python["adapter_file"]).resolve(),
        core_module_path=Path(python["core_file"]).resolve(),
        profile=profile,
        packages_dir=packages,
        package_file=package_file,
        install_root=install_root,
        receipt_path=receipt_path,
        bootstrap_log_dir=profile / ".dcc-mcp" / "logs",
        state=state,
        receipt=receipt,
    )


def _base_result(ctx: InstallContext, status: str) -> dict[str, Any]:
    return {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": status,
        "dcc_type": DCC_TYPE,
        "adapter_version": __version__,
        "core_version": ctx.core_version,
        "steps": [],
        "next_steps": [],
        "receipt_path": str(ctx.receipt_path),
        "verify": {"directly_usable": False, "failure_stage": None, "failure_reason": None},
        "install_state": ctx.state,
        "plan": {
            "host_path": str(ctx.host_path),
            "host_version": ctx.host_version,
            "host_version_source": ctx.host_version_source,
            "interpreter": str(ctx.python_path),
            "interpreter_source": ctx.python_source,
            "python_version": ctx.python_version,
            "profile_path": str(ctx.profile),
            "packages_dir": str(ctx.packages_dir),
            "install_root": str(ctx.install_root),
            "state": ctx.state,
            "min_core_version": MIN_CORE_VERSION,
            "min_host_version": "18.5",
        },
    }


def _command(ctx: InstallContext, verb: str, execute: bool = False) -> list[str]:
    command = [COMMAND, verb, "--json"]
    if execute:
        command.append("--yes")
    command.extend(("--dcc-path", str(ctx.host_path), "--python", str(ctx.python_path)))
    return command


def _plan(ctx: InstallContext, verb: str) -> LifecycleOutcome:
    result = _base_result(ctx, "planned")
    if verb in ("install", "upgrade"):
        result["steps"] = [
            {"id": "preflight", "status": "ok"},
            {"id": "install", "status": "planned"},
            {"id": "verify", "status": "planned"},
        ]
        result["next_steps"] = [
            {
                "id": "execute",
                "description": "Execute the validated Houdini {} plan.".format(verb),
                "command": _command(ctx, verb, execute=True),
                "why": "Planning does not modify Houdini or the install receipt.",
            }
        ]
    else:
        result["steps"] = [
            {"id": "receipt", "status": "ok" if ctx.receipt_path.is_file() else "absent"},
            {"id": "uninstall", "status": "planned"},
        ]
        result["next_steps"] = [
            {
                "id": "execute_uninstall",
                "description": "Remove only the receipted Houdini package and startup files.",
                "command": _command(ctx, "uninstall", execute=True),
                "why": "Planning does not modify the versioned Houdini profile.",
            }
        ]
    return LifecycleOutcome(result, INSTALL_EXIT_OK)


def _receipt(ctx: InstallContext, installed_at: float) -> dict[str, Any]:
    directories, owned_files, links = _owned_root_manifest(ctx.install_root)
    package_record = _file_record(ctx.package_file)
    compatibility_files = [
        {
            "path": str((ctx.install_root / item["path"]).resolve()),
            "sha256": item["sha256"],
            "size": item["size"],
        }
        for item in owned_files
    ]
    compatibility_files.append(package_record)
    previous = ctx.receipt or {}
    return {
        "schema_version": 1,
        "dcc_type": DCC_TYPE,
        "adapter_version": __version__,
        "core_version": ctx.core_version,
        "host": {"path": str(ctx.host_path), "version": ctx.host_version, "root": str(_host_root(ctx.host_path))},
        "python": {
            "path": str(ctx.python_path),
            "version": ctx.python_version,
            "hou_module_path": str(ctx.hou_module_path),
            "adapter_module_path": str(ctx.adapter_module_path),
            "core_module_path": str(ctx.core_module_path),
        },
        "profile_path": str(ctx.profile),
        "install_root": str(ctx.install_root),
        "package_file": str(ctx.package_file),
        "bootstrap_log_dir": str(ctx.bootstrap_log_dir),
        "installed_at_epoch": installed_at,
        "previous_adapter_version": previous.get("adapter_version"),
        "files": compatibility_files,
        "ownership": {
            "directories": directories,
            "files": owned_files,
            "links": links,
            "package_file": package_record,
        },
        "server": {"registry_type": DCC_TYPE, "probe_tool": _READINESS_TOOL},
    }


def _readiness_steps(
    ctx: InstallContext,
    *,
    instance_id: Optional[str] = None,
    host_pid: Optional[int] = None,
) -> list[dict[str, Any]]:
    verify_command = _command(ctx, "verify")
    if instance_id:
        verify_command.extend(("--instance-id", instance_id))
    if host_pid:
        verify_command.extend(("--host-pid", str(host_pid)))
    return [
        {
            "id": "start_selected_houdini",
            "description": "Start the exact selected Houdini executable.",
            "command": [str(ctx.host_path)],
            "why": "Readiness must come from the selected Houdini build, not an unrelated registry entry.",
        },
        {
            "id": "verify_selected_houdini",
            "description": "Verify the selected Houdini instance with the typed HOM probe.",
            "command": verify_command,
            "why": "A live host-bound probe is required before the adapter is directly usable.",
        },
    ]


def _entry_host_pid(entry: Mapping[str, Any]) -> Optional[int]:
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    value = metadata.get("dcc_pid") or metadata.get("host_pid") or entry.get("runtime_pid")
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _probe_context(readiness: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    probe = readiness.get("probe")
    result = probe.get("result") if isinstance(probe, dict) else None
    if not isinstance(result, dict):
        return None
    structured = result.get("structuredContent")
    if structured is None:
        structured = result.get("structured_content")
    if not isinstance(structured, dict) or structured.get("success") is not True:
        return None
    context = structured.get("context")
    return context if isinstance(context, dict) else None


def _runtime_identity_failure(
    readiness: Mapping[str, Any],
    ctx: InstallContext,
    *,
    instance_id: Optional[str],
    host_pid: Optional[int],
) -> Optional[str]:
    entry = readiness.get("entry")
    if not isinstance(entry, dict):
        return "Ready response did not identify one Houdini sidecar instance."
    actual_instance = entry.get("instance_id")
    if not isinstance(actual_instance, str) or not actual_instance.strip():
        return "Ready response omitted the Houdini instance id."
    if instance_id is not None and actual_instance != instance_id:
        return "Ready response belongs to a different Houdini instance."
    actual_pid = _entry_host_pid(entry)
    if actual_pid is None:
        return "Ready response omitted the Houdini host PID."
    if host_pid is not None and actual_pid != host_pid:
        return "Ready response belongs to a different Houdini host PID."
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    entry_version = metadata.get("dcc_version") or entry.get("version")
    if _version_tuple(entry_version) is None or entry_version != ctx.host_version:
        return "Ready response Houdini version does not match the selected installation."
    entry_adapter = entry.get("adapter_version") or metadata.get("adapter_version")
    if _version_tuple(entry_adapter) is None or entry_adapter != __version__:
        return "Ready response adapter version does not match this installation."
    process_path = _process_executable_path(actual_pid)
    if process_path is None or not _same_path(process_path, ctx.host_path):
        return "Ready Houdini process path differs from the selected executable."
    process_start = _process_start_identity(actual_pid)
    if process_start is None:
        return "Ready Houdini process start identity could not be established."

    context = _probe_context(readiness)
    if context is None:
        return "Ready response omitted the real HOM structured payload."
    try:
        probe_pid = int(context.get("host_pid"))
    except (TypeError, ValueError):
        return "Real HOM payload omitted the Houdini host PID."
    if probe_pid != actual_pid:
        return "Real HOM payload host PID differs from the selected sidecar instance."
    if context.get("process_start_identity") != process_start:
        return "Real HOM payload process start identity differs from the selected process."
    if context.get("houdini_version_string") != ctx.host_version:
        return "Real HOM payload Houdini version differs from the selected installation."
    if context.get("adapter_version") != __version__:
        return "Real HOM payload adapter version differs from this installation."
    if not bool(context.get("ui_available")):
        return "Real HOM payload did not come from an interactive Houdini session."
    expected_paths = {
        "host_executable": ctx.host_path,
        "houdini_root": _host_root(ctx.host_path),
        "hou_module_path": ctx.hou_module_path,
        "adapter_module_path": ctx.adapter_module_path,
        "core_module_path": ctx.core_module_path,
    }
    for key, expected in expected_paths.items():
        value = context.get(key)
        if not value:
            return "Real HOM payload omitted {}.".format(key)
        try:
            if not _same_path(Path(str(value)), expected):
                return "Real HOM payload {} differs from the selected installation.".format(key)
        except OSError:
            return "Real HOM payload {} is invalid.".format(key)
    return None


def _verify(
    ctx: InstallContext,
    environ: Mapping[str, str],
    *,
    instance_id: Optional[str] = None,
    host_pid: Optional[int] = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not ctx.receipt_path.is_file():
        return {
            "directly_usable": False,
            "failure_stage": "receipt",
            "failure_reason": "No Houdini install receipt exists.",
        }, []
    if ctx.state in ("partial", "repair"):
        return {
            "directly_usable": False,
            "failure_stage": "install_state",
            "failure_reason": "Houdini package state is {}.".format(ctx.state),
        }, []
    receipt = _load_json(ctx.receipt_path)
    if receipt.get("dcc_type") != DCC_TYPE:
        return {
            "directly_usable": False,
            "failure_stage": "receipt",
            "failure_reason": "The receipt belongs to another adapter.",
        }, []
    try:
        _validate_owned_install(ctx.install_root, ctx.package_file, ctx.receipt_path, receipt)
    except LifecycleFailure as exc:
        return {
            "directly_usable": False,
            "failure_stage": "artifact",
            "failure_reason": str(exc),
        }, []
    try:
        _query_python(ctx.python_path, ctx.host_path)
    except LifecycleFailure as exc:
        return {"directly_usable": False, "failure_stage": "import", "failure_reason": str(exc)}, []
    installed_at = float(receipt.get("installed_at_epoch", 0.0))
    errors = (
        [path for path in ctx.bootstrap_log_dir.glob("*.host-errors.log") if path.stat().st_mtime >= installed_at]
        if ctx.bootstrap_log_dir.is_dir()
        else []
    )
    if errors:
        return {
            "directly_usable": False,
            "failure_stage": "bootstrap",
            "failure_reason": "Houdini captured a bootstrap failure in {}".format(errors[-1]),
        }, []
    timeout = max(0.05, float(environ.get("DCC_MCP_INSTALL_VERIFY_TIMEOUT", "2.0")))
    runtime = query_runtime_state(environ.get("DCC_MCP_REGISTRY_DIR"), dcc_type=DCC_TYPE, include_dead=False)
    entries = [entry for entry in runtime.get("entries", []) if isinstance(entry, dict) and entry.get("mcp_url")]
    if instance_id is not None:
        entries = [entry for entry in entries if entry.get("instance_id") == instance_id]
    if host_pid is not None:
        entries = [entry for entry in entries if _entry_host_pid(entry) == host_pid]
    if len(entries) != 1:
        reason = (
            "No live Houdini adapter is registered."
            if not entries
            else "Multiple live Houdini adapters are registered."
        )
        return {
            "directly_usable": False,
            "failure_stage": "readiness",
            "failure_reason": reason,
            "probe_tool": _READINESS_TOOL,
        }, _readiness_steps(ctx, instance_id=instance_id, host_pid=host_pid)
    selected = entries[0]
    selected_instance = selected.get("instance_id")
    if not isinstance(selected_instance, str) or not selected_instance.strip():
        return {
            "directly_usable": False,
            "failure_stage": "readiness_identity",
            "failure_reason": "Selected Houdini registry entry omitted its instance id.",
            "probe_tool": _READINESS_TOOL,
        }, _readiness_steps(ctx, instance_id=instance_id, host_pid=host_pid)
    ready = wait_for_sidecar_ready(
        environ.get("DCC_MCP_REGISTRY_DIR"),
        dcc_type=DCC_TYPE,
        instance_id=selected_instance,
        timeout_secs=timeout,
        poll_interval_secs=min(timeout, 0.1),
        probe_tool=_READINESS_TOOL,
        probe_timeout_secs=timeout,
    )
    if not ready.get("success"):
        return {
            "directly_usable": False,
            "failure_stage": "readiness",
            "failure_reason": str(ready.get("message") or ready.get("status") or "Typed Houdini probe failed."),
            "probe_tool": _READINESS_TOOL,
        }, _readiness_steps(ctx, instance_id=selected_instance, host_pid=_entry_host_pid(selected))
    identity_failure = _runtime_identity_failure(
        ready,
        ctx,
        instance_id=selected_instance,
        host_pid=_entry_host_pid(selected),
    )
    if identity_failure is not None:
        return {
            "directly_usable": False,
            "failure_stage": "readiness_identity",
            "failure_reason": identity_failure,
            "probe_tool": _READINESS_TOOL,
        }, _readiness_steps(ctx, instance_id=selected_instance, host_pid=_entry_host_pid(selected))
    return {
        "directly_usable": True,
        "failure_stage": None,
        "failure_reason": None,
        "probe_tool": _READINESS_TOOL,
    }, []


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _move_path(source: Path, destination: Path) -> bool:
    if not _path_exists(source):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(source), str(destination))
    return True


def _restore_install_transaction(
    ctx: InstallContext,
    transaction: Path,
    backup_root: Path,
    backup_package: Path,
    backup_receipt: Path,
    *,
    remove_unbacked_current: bool,
) -> bool:
    restored_previous = any(_path_exists(path) for path in (backup_root, backup_package, backup_receipt))
    failed = transaction / "failed"
    for current, backup, name in (
        (ctx.receipt_path, backup_receipt, "receipt.json"),
        (ctx.package_file, backup_package, _PACKAGE_FILE),
        (ctx.install_root, backup_root, _INSTALL_DIR),
    ):
        if _path_exists(current) and (_path_exists(backup) or remove_unbacked_current):
            _move_path(current, failed / name)
        if _path_exists(backup):
            _move_path(backup, current)
    if ctx.receipt_path.is_file():
        prior = _load_json(ctx.receipt_path)
        _validate_owned_install(ctx.install_root, ctx.package_file, ctx.receipt_path, prior)
    elif any(_path_exists(path) for path in (ctx.install_root, ctx.package_file)):
        raise LifecycleFailure("install", "Install rollback left unreceipted managed state.", INSTALL_EXIT_INSTALL)
    return restored_previous


def _cleanup_transaction(path: Path) -> dict[str, Any]:
    try:
        result = safe_remove_tree(path)
    except BaseException as exc:
        return {"success": False, "requires_restart": False, "message": exc.__class__.__name__}
    return result if isinstance(result, dict) else {"success": False, "requires_restart": False}


def _execute_install(
    ctx: InstallContext,
    environ: Mapping[str, str],
    *,
    instance_id: Optional[str] = None,
    host_pid: Optional[int] = None,
) -> LifecycleOutcome:
    if ctx.state in ("partial", "repair"):
        raise LifecycleFailure(ctx.state, "Unowned or changed Houdini package state cannot be overwritten.")
    inspection = inspect_install_root(ctx.install_root)
    if inspection.get("requires_restart"):
        result = _base_result(ctx, "requires_restart")
        result["steps"] = [{"id": "preflight", "status": "requires_restart"}]
        result["lock"] = inspection
        result["next_steps"] = [
            {
                "id": "retry_after_restart",
                "description": "Close Houdini and repeat the install.",
                "command": _command(ctx, "install", execute=True),
                "why": "Core found a loaded artifact under the managed install root.",
            }
        ]
        return LifecycleOutcome(result, INSTALL_EXIT_REQUIRES_RESTART)

    transaction = ctx.profile / ".dcc-mcp" / "staging" / uuid.uuid4().hex
    staged = transaction / "payload" / _INSTALL_DIR
    backup_root = transaction / "backup" / _INSTALL_DIR
    backup_package = transaction / "backup" / _PACKAGE_FILE
    backup_receipt = transaction / "backup" / "houdini.json"
    committed = False
    mutation_started = False
    try:
        for relative, content in _expected_sources(ctx).items():
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        expected = _package_payload(ctx.install_root)
        _move_path(ctx.install_root, backup_root)
        _move_path(ctx.package_file, backup_package)
        _move_path(ctx.receipt_path, backup_receipt)
        mutation_started = True
        replaced = safe_replace_tree(staged, ctx.install_root)
        if not replaced.get("success"):
            code = INSTALL_EXIT_REQUIRES_RESTART if replaced.get("requires_restart") else INSTALL_EXIT_INSTALL
            raise LifecycleFailure("install", str(replaced.get("message") or "Staged replace failed."), code)
        _write_text_atomic(ctx.package_file, expected)
        _write_json_atomic(ctx.receipt_path, _receipt(ctx, time.time()))
        verify, next_steps = _verify(
            ctx,
            environ,
            instance_id=instance_id,
            host_pid=host_pid,
        )
        if not verify["directly_usable"]:
            restored = _restore_install_transaction(
                ctx,
                transaction,
                backup_root,
                backup_package,
                backup_receipt,
                remove_unbacked_current=True,
            )
            cleanup = _cleanup_transaction(transaction)
            if not cleanup.get("success"):
                raise LifecycleFailure(
                    "install",
                    "Install verification failed; prior state was restored but transaction cleanup failed.",
                    INSTALL_EXIT_INSTALL,
                )
            result = _base_result(ctx, "failed")
            result["steps"] = [
                {"id": "preflight", "status": "ok"},
                {"id": "install", "status": "rolled_back"},
                {"id": "receipt", "status": "rolled_back"},
                {"id": "verify", "status": "failed"},
            ]
            result["verify"] = verify
            result["next_steps"] = next_steps
            result["previous_restored"] = restored
            return LifecycleOutcome(result, INSTALL_EXIT_VERIFY)
        committed = True
        cleanup = _cleanup_transaction(transaction)
        if not cleanup.get("success"):
            raise LifecycleFailure(
                "install",
                "The verified install is usable, but transaction cleanup failed.",
                INSTALL_EXIT_REQUIRES_RESTART if cleanup.get("requires_restart") else INSTALL_EXIT_INSTALL,
            )
    except BaseException as exc:
        if not committed and _path_exists(transaction):
            try:
                _restore_install_transaction(
                    ctx,
                    transaction,
                    backup_root,
                    backup_package,
                    backup_receipt,
                    remove_unbacked_current=mutation_started,
                )
            except BaseException as restore_error:
                raise LifecycleFailure(
                    "install",
                    "Install failed and the prior managed state could not be restored.",
                    INSTALL_EXIT_INSTALL,
                ) from restore_error
            _cleanup_transaction(transaction)
        raise exc

    result = _base_result(ctx, "ok" if verify["directly_usable"] else "partial")
    result["steps"] = [
        {"id": "preflight", "status": "ok"},
        {"id": "install", "status": "ok"},
        {"id": "receipt", "status": "ok"},
        {"id": "verify", "status": "ok" if verify["directly_usable"] else "failed"},
    ]
    result["verify"] = verify
    result["next_steps"] = next_steps
    return LifecycleOutcome(result, INSTALL_EXIT_OK if verify["directly_usable"] else INSTALL_EXIT_VERIFY)


def _snapshot_matches(snapshot_root: Path, snapshot_package: Path, receipt: Mapping[str, Any]) -> bool:
    ownership = receipt.get("ownership") if isinstance(receipt.get("ownership"), dict) else {}
    directories, files, links = _owned_root_manifest(snapshot_root)
    package = _file_record(snapshot_package)
    expected_package = ownership.get("package_file") if isinstance(ownership, dict) else None
    return bool(
        directories == ownership.get("directories")
        and files == ownership.get("files")
        and links == ownership.get("links")
        and isinstance(expected_package, dict)
        and package.get("sha256") == expected_package.get("sha256")
        and package.get("size") == expected_package.get("size")
    )


def _capture_owned_bytes(
    ctx: InstallContext,
    receipt: Mapping[str, Any],
) -> tuple[list[str], dict[str, bytes], bytes, bytes]:
    ownership = receipt["ownership"]
    directories = list(ownership["directories"])
    projected_size = sum(int(record["size"]) for record in ownership["files"])
    projected_size += int(ownership["package_file"]["size"]) + ctx.receipt_path.stat().st_size
    if projected_size > _MAX_TRANSACTION_SNAPSHOT_BYTES:
        raise LifecycleFailure("uninstall", "Managed install is too large for bounded rollback.", INSTALL_EXIT_INSTALL)
    files = {}
    total = 0
    for record in ownership["files"]:
        relative = str(record["path"])
        data = (ctx.install_root / relative).read_bytes()
        total += len(data)
        files[relative] = data
    package = ctx.package_file.read_bytes()
    receipt_bytes = ctx.receipt_path.read_bytes()
    total += len(package) + len(receipt_bytes)
    if total > _MAX_TRANSACTION_SNAPSHOT_BYTES:
        raise LifecycleFailure("uninstall", "Managed install is too large for bounded rollback.", INSTALL_EXIT_INSTALL)
    return directories, files, package, receipt_bytes


def _restore_uninstall_bytes(
    ctx: InstallContext,
    transaction: Path,
    receipt: Mapping[str, Any],
    directories: Sequence[str],
    files: Mapping[str, bytes],
    package: bytes,
    receipt_bytes: bytes,
) -> None:
    failed = transaction / "failed"
    for current, name in (
        (ctx.install_root, _INSTALL_DIR),
        (ctx.package_file, _PACKAGE_FILE),
        (ctx.receipt_path, "houdini.json"),
    ):
        if _path_exists(current):
            _move_path(current, failed / name)
    ctx.install_root.mkdir(parents=True, exist_ok=True)
    for relative in sorted(directories, key=lambda value: (len(Path(value).parts), value)):
        (ctx.install_root / relative).mkdir()
    for relative, data in files.items():
        path = ctx.install_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    ctx.package_file.parent.mkdir(parents=True, exist_ok=True)
    ctx.package_file.write_bytes(package)
    ctx.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.receipt_path.write_bytes(receipt_bytes)
    _validate_owned_install(ctx.install_root, ctx.package_file, ctx.receipt_path, receipt)


def _execute_uninstall(ctx: InstallContext) -> LifecycleOutcome:
    if not ctx.receipt_path.is_file():
        if ctx.install_root.exists() or ctx.package_file.exists():
            raise LifecycleFailure("partial", "Unreceipted Houdini package state cannot be removed safely.")
        result = _base_result(ctx, "ok")
        result["steps"] = [{"id": "uninstall", "status": "already_absent"}]
        return LifecycleOutcome(result, INSTALL_EXIT_OK)
    receipt = _load_json(ctx.receipt_path)
    _validate_owned_install(ctx.install_root, ctx.package_file, ctx.receipt_path, receipt)
    snapshot_directories, snapshot_files, package_bytes, receipt_bytes = _capture_owned_bytes(ctx, receipt)
    inspection = inspect_install_root(ctx.install_root)
    if inspection.get("requires_restart"):
        result = _base_result(ctx, "requires_restart")
        result["steps"] = [{"id": "uninstall", "status": "requires_restart"}]
        result["lock"] = inspection
        result["next_steps"] = [
            {
                "id": "retry_uninstall",
                "description": "Close Houdini and repeat the receipt-driven uninstall.",
                "command": _command(ctx, "uninstall", execute=True),
                "why": "Core found a loaded artifact under the receipted install root.",
            }
        ]
        return LifecycleOutcome(result, INSTALL_EXIT_REQUIRES_RESTART)

    transaction = ctx.profile / ".dcc-mcp" / "staging" / uuid.uuid4().hex
    snapshot_root = transaction / "snapshot" / _INSTALL_DIR
    snapshot_package = transaction / "snapshot" / _PACKAGE_FILE
    snapshot_receipt = transaction / "snapshot" / "houdini.json"
    quarantine_root = transaction / "quarantine" / _INSTALL_DIR
    quarantine_package = transaction / "quarantine" / _PACKAGE_FILE
    quarantine_receipt = transaction / "quarantine" / "houdini.json"
    snapshot_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(str(ctx.install_root), str(snapshot_root))
        shutil.copy2(str(ctx.package_file), str(snapshot_package))
        shutil.copy2(str(ctx.receipt_path), str(snapshot_receipt))
        if not _snapshot_matches(snapshot_root, snapshot_package, receipt):
            raise LifecycleFailure("uninstall", "Uninstall snapshot verification failed.", INSTALL_EXIT_INSTALL)
        _move_path(ctx.install_root, quarantine_root)
        _move_path(ctx.package_file, quarantine_package)
        _move_path(ctx.receipt_path, quarantine_receipt)
        removed = _cleanup_transaction(transaction / "quarantine")
        if not removed.get("success"):
            _restore_uninstall_bytes(
                ctx,
                transaction,
                receipt,
                snapshot_directories,
                snapshot_files,
                package_bytes,
                receipt_bytes,
            )
            _cleanup_transaction(transaction)
            code = INSTALL_EXIT_REQUIRES_RESTART if removed.get("requires_restart") else INSTALL_EXIT_INSTALL
            raise LifecycleFailure(
                "uninstall",
                "Uninstall failed; the complete prior installation was restored.",
                code,
            )
        cleanup = _cleanup_transaction(transaction)
        if not cleanup.get("success"):
            _restore_uninstall_bytes(
                ctx,
                transaction,
                receipt,
                snapshot_directories,
                snapshot_files,
                package_bytes,
                receipt_bytes,
            )
            _cleanup_transaction(transaction)
            raise LifecycleFailure(
                "uninstall",
                "Uninstall cleanup failed; the complete prior installation was restored.",
                INSTALL_EXIT_REQUIRES_RESTART if cleanup.get("requires_restart") else INSTALL_EXIT_INSTALL,
            )
    except BaseException as exc:
        needs_restore = False
        try:
            _validate_owned_install(ctx.install_root, ctx.package_file, ctx.receipt_path, receipt)
        except LifecycleFailure:
            needs_restore = True
        if needs_restore:
            try:
                _restore_uninstall_bytes(
                    ctx,
                    transaction,
                    receipt,
                    snapshot_directories,
                    snapshot_files,
                    package_bytes,
                    receipt_bytes,
                )
            except BaseException as restore_error:
                raise LifecycleFailure(
                    "uninstall",
                    "Uninstall failed and the prior managed state could not be restored.",
                    INSTALL_EXIT_INSTALL,
                ) from restore_error
        _cleanup_transaction(transaction)
        if isinstance(exc, LifecycleFailure):
            raise exc
        raise LifecycleFailure(
            "uninstall",
            "Uninstall failed; the complete prior installation was preserved or restored.",
            INSTALL_EXIT_INSTALL,
        ) from exc
    result = _base_result(ctx, "ok")
    result["steps"] = [{"id": "receipt", "status": "consumed"}, {"id": "uninstall", "status": "ok"}]
    return LifecycleOutcome(result, INSTALL_EXIT_OK)


def _status(ctx: InstallContext) -> LifecycleOutcome:
    incomplete = ctx.state in ("partial", "repair")
    result = _base_result(ctx, "partial" if incomplete else "ok")
    result["steps"] = [
        {"id": "receipt", "status": "ok" if ctx.receipt_path.is_file() else "absent"},
        {"id": "artifacts", "status": ctx.state},
    ]
    if incomplete:
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "install_state",
            "failure_reason": "Houdini package state is {}.".format(ctx.state),
        }
    return LifecycleOutcome(result, INSTALL_EXIT_PREFLIGHT if incomplete else INSTALL_EXIT_OK)


def _verify_outcome(
    ctx: InstallContext,
    environ: Mapping[str, str],
    *,
    instance_id: Optional[str] = None,
    host_pid: Optional[int] = None,
) -> LifecycleOutcome:
    verify, next_steps = _verify(ctx, environ, instance_id=instance_id, host_pid=host_pid)
    result = _base_result(ctx, "ok" if verify["directly_usable"] else "failed")
    result["steps"] = [{"id": "verify", "status": "ok" if verify["directly_usable"] else "failed"}]
    result["verify"] = verify
    result["next_steps"] = next_steps
    return LifecycleOutcome(result, INSTALL_EXIT_OK if verify["directly_usable"] else INSTALL_EXIT_VERIFY)


def _failure_result(
    dcc_path: Optional[str],
    python_path: Optional[str],
    environ: Mapping[str, str],
    failure: LifecycleFailure,
) -> LifecycleOutcome:
    packages = environ.get(_PACKAGES_ENV)
    receipt = (
        Path(packages).expanduser().resolve().parent / ".dcc-mcp" / "receipts" / "houdini.json" if packages else None
    )
    remediation = [COMMAND, "install", "--json", "--dry-run"]
    remediation_id = "rediscover_install_plan"
    remediation_description = "Rediscover Houdini and produce a fresh non-mutating install plan."
    selected_python = python_path or environ.get(_PYTHON_ENV)
    selected_hython = None
    if selected_python:
        try:
            candidate = Path(selected_python)
            if candidate.name.lower() in _HYTHON_EXECUTABLES and candidate.is_file() and candidate.stat().st_size > 0:
                selected_hython = str(candidate.resolve())
        except OSError:
            selected_hython = None
    if failure.stage == "core_version" and selected_hython:
        remediation = [
            selected_hython,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "dcc-mcp-core>={},<1.0.0".format(MIN_CORE_VERSION),
        ]
        remediation_id = "upgrade_core_in_selected_hython"
        remediation_description = "Install the supported Core floor into the selected Hython interpreter."
    elif failure.stage == "python" and selected_hython:
        remediation = [
            selected_hython,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "dcc-mcp-houdini=={}".format(__version__),
        ]
        remediation_id = "repair_selected_hython"
        remediation_description = "Install this adapter and its dependencies into the selected Hython interpreter."
    result = {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": "requires_restart" if failure.exit_code == INSTALL_EXIT_REQUIRES_RESTART else "failed",
        "dcc_type": DCC_TYPE,
        "adapter_version": __version__,
        "core_version": (
            str(getattr(dcc_mcp_core, "__version__", "unknown"))
            if _version_tuple(getattr(dcc_mcp_core, "__version__", None)) is not None
            else "unknown"
        ),
        "steps": [{"id": "preflight", "status": "failed", "message": _bounded_text(failure)}],
        "next_steps": [
            {
                "id": remediation_id,
                "description": remediation_description,
                "command": remediation,
                "why": _bounded_text(failure),
            }
        ],
        "receipt_path": str(receipt) if receipt else None,
        "verify": {
            "directly_usable": False,
            "failure_stage": failure.stage,
            "failure_reason": _bounded_text(failure),
        },
    }
    return LifecycleOutcome(result, failure.exit_code)


def run_lifecycle(
    verb: str,
    *,
    dcc_path: Optional[str],
    python_path: Optional[str],
    yes: bool,
    dry_run: bool,
    instance_id: Optional[str] = None,
    host_pid: Optional[int] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> LifecycleOutcome:
    """Run one standard lifecycle verb without importing ``hou`` in this process."""
    resolved_environ = os.environ if environ is None else environ
    try:
        ctx = _resolve_context(dcc_path, python_path, resolved_environ)
        if verb == "status":
            return _status(ctx)
        if verb == "verify":
            return _verify_outcome(
                ctx,
                resolved_environ,
                instance_id=instance_id,
                host_pid=host_pid,
            )
        if verb == "uninstall":
            return _plan(ctx, verb) if dry_run or not yes else _execute_uninstall(ctx)
        if verb in ("install", "upgrade"):
            if verb == "upgrade" and ctx.state == "fresh":
                raise LifecycleFailure("upgrade", "Nothing is installed; use install for a fresh Houdini profile.")
            return (
                _plan(ctx, verb)
                if dry_run or not yes
                else _execute_install(
                    ctx,
                    resolved_environ,
                    instance_id=instance_id,
                    host_pid=host_pid,
                )
            )
        raise LifecycleFailure("verb", "Unsupported lifecycle verb: {}".format(verb))
    except LifecycleFailure as exc:
        return _failure_result(dcc_path, python_path, resolved_environ, exc)
    except Exception as exc:
        return _failure_result(
            dcc_path,
            python_path,
            resolved_environ,
            LifecycleFailure("install", "Lifecycle operation failed: {}".format(exc), INSTALL_EXIT_INSTALL),
        )


__all__ = [
    "COMMAND",
    "DCC_TYPE",
    "LIFECYCLE_COMMANDS",
    "MIN_CORE_VERSION",
    "MIN_HOUDINI_VERSION",
    "LifecycleOutcome",
    "run_lifecycle",
]
