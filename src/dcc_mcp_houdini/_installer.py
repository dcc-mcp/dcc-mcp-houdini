"""Houdini-owned Install SOP lifecycle built on public Core primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import dcc_mcp_core
from dcc_mcp_core import (
    inspect_install_root,
    query_runtime_state,
    safe_remove_tree,
    safe_replace_tree,
    wait_for_sidecar_ready,
)

from dcc_mcp_houdini.__version__ import __version__
from dcc_mcp_houdini._install_contract import (
    INSTALL_EXIT_INSTALL,
    INSTALL_EXIT_OK,
    INSTALL_EXIT_PREFLIGHT,
    INSTALL_EXIT_REQUIRES_RESTART,
    INSTALL_EXIT_VERIFY,
    INSTALL_SOP_SCHEMA_VERSION,
)

DCC_TYPE = "houdini"
COMMAND = "dcc-mcp-houdini"
MIN_CORE_VERSION = "0.19.70"
MIN_HOUDINI_VERSION = (18, 5)
LIFECYCLE_COMMANDS = frozenset(("install", "status", "verify", "uninstall", "upgrade"))

_PYTHON_ENV = "DCC_MCP_INSTALL_PYTHON"
_PACKAGES_ENV = "DCC_MCP_HOUDINI_PACKAGES_DIR"
_INSTALL_DIR = "dcc-mcp-houdini"
_PACKAGE_FILE = "dcc_mcp_houdini.json"
_READINESS_TOOL = "houdini_scripting__get_session_info"
_VERSION_RE = re.compile(r"Houdini[ _-]?(?P<version>\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)


@dataclass(frozen=True)
class InstallContext:
    host_path: Path
    host_version: str
    host_version_source: str
    python_path: Path
    python_source: str
    python_version: str
    core_version: str
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


def _version_tuple(value: object) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", str(value or ""))
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
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
            names = ("houdini.exe", "houdini", "hython.exe", "hython")
            nested = [candidate / "bin" / name for name in names]
            nested.extend(candidate / name for name in names)
            matches = [path for path in nested if path.is_file()]
            if len(matches) == 1:
                candidate = matches[0]
            elif matches:
                candidate = next((path for path in matches if path.name.lower().startswith("houdini")), matches[0])
        if candidate.is_file():
            return candidate
        raise LifecycleFailure("host", "Houdini executable does not exist: {}".format(candidate))
    candidates = _host_candidates(environ)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise LifecycleFailure("host", "Houdini was not found; pass its exact executable with --dcc-path.")
    raise LifecycleFailure("host", "Multiple Houdini installations were found; select one with --dcc-path.")


def _host_version(path: Path) -> tuple[str, str]:
    for text in (str(path), path.parent.name, path.parent.parent.name):
        match = _VERSION_RE.search(text)
        if match:
            return match.group("version"), "path"
    return "", "unavailable"


def _host_root(path: Path) -> Path:
    if path.parent.name.lower() == "bin":
        return path.parent.parent
    return path.parent


def _resolve_python(value: Optional[str], host: Path, environ: Mapping[str, str]) -> tuple[Path, str]:
    configured = value or environ.get(_PYTHON_ENV)
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise LifecycleFailure("python", "Target interpreter does not exist: {}".format(path))
        return path, "--python" if value else _PYTHON_ENV
    if host.name.lower().startswith("hython"):
        return host, "selected_host"
    executable = "hython.exe" if os.name == "nt" else "hython"
    candidate = _host_root(host) / "bin" / executable
    if candidate.is_file():
        return candidate.resolve(), "host_install"
    raise LifecycleFailure(
        "python",
        "Houdini's hython interpreter was not found; pass its exact executable with --python.",
    )


def _query_python(path: Path) -> dict[str, str]:
    script = (
        "import json,sys; import hou; import dcc_mcp_core,dcc_mcp_houdini as adapter; "
        "print(json.dumps({'python_version':'.'.join(map(str,sys.version_info[:3])),"
        "'core_version':dcc_mcp_core.__version__,'adapter_version':adapter.__version__,"
        "'host_version':hou.applicationVersionString(),'executable':sys.executable}))"
    )
    try:
        completed = subprocess.run(
            [str(path), "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleFailure("python", "Target interpreter could not run: {}".format(exc)) from exc
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip().splitlines()
        detail = details[-1] if details else "exit {}".format(completed.returncode)
        raise LifecycleFailure("python", "Target interpreter import check failed: {}".format(detail))
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise LifecycleFailure("python", "Target interpreter returned invalid metadata.") from exc
    if result.get("adapter_version") != __version__:
        raise LifecycleFailure(
            "python",
            "Target interpreter has adapter {!r}; expected {!r}.".format(result.get("adapter_version"), __version__),
        )
    if _version_tuple(result.get("core_version")) < _version_tuple(MIN_CORE_VERSION):
        raise LifecycleFailure("core_version", "dcc-mcp-core>={} is required.".format(MIN_CORE_VERSION))
    if _version_tuple(result.get("python_version")) < (3, 7):
        raise LifecycleFailure("python_version", "Houdini Python 3.7 or newer is required.")
    return {str(key): "" if value is None else str(value) for key, value in result.items()}


def _profile_paths(host_version: str, environ: Mapping[str, str]) -> tuple[Path, Path]:
    override = environ.get(_PACKAGES_ENV, "").strip()
    if override:
        packages = Path(override).expanduser().resolve()
        return packages.parent, packages
    short_version = ".".join(str(part) for part in _version_tuple(host_version)[:2])
    if not short_version:
        raise LifecycleFailure("host_version", "The Houdini profile version could not be resolved.")
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
    intact = package_file.is_file() and package_file.read_text(encoding="utf-8") == expected_package
    files = receipt.get("files")
    if not isinstance(files, list) or not files:
        return "partial", receipt
    expected_files = {path.resolve() for path in install_root.rglob("*") if path.is_file()}
    if package_file.is_file():
        expected_files.add(package_file.resolve())
    recorded_files = {
        Path(str(item.get("path", ""))).resolve() for item in files if isinstance(item, dict) and item.get("path")
    }
    if recorded_files != expected_files:
        intact = False
    for item in files:
        if not isinstance(item, dict):
            intact = False
            continue
        path = Path(str(item.get("path", "")))
        if not path.is_file() or _hash_file(path) != item.get("sha256"):
            intact = False
    if receipt.get("adapter_version") != __version__:
        return "upgrade", receipt
    return ("current" if intact else "repair"), receipt


def _resolve_context(
    dcc_path: Optional[str],
    python_path: Optional[str],
    environ: Mapping[str, str],
) -> InstallContext:
    host = _resolve_host(dcc_path, environ)
    host_version, host_source = _host_version(host)
    interpreter, python_source = _resolve_python(python_path, host, environ)
    python = _query_python(interpreter)
    embedded_version = python.get("host_version", "")
    if embedded_version:
        if host_version and _version_tuple(host_version)[:2] != _version_tuple(embedded_version)[:2]:
            raise LifecycleFailure(
                "host_version",
                "Selected host {} does not match hython {}.".format(host_version, embedded_version),
            )
        host_version, host_source = embedded_version, "hython"
    if not host_version or _version_tuple(host_version) < MIN_HOUDINI_VERSION:
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
    files = sorted(path for path in ctx.install_root.rglob("*") if path.is_file())
    files.append(ctx.package_file)
    previous = ctx.receipt or {}
    return {
        "schema_version": 1,
        "dcc_type": DCC_TYPE,
        "adapter_version": __version__,
        "core_version": ctx.core_version,
        "host": {"path": str(ctx.host_path), "version": ctx.host_version},
        "python": {"path": str(ctx.python_path), "version": ctx.python_version},
        "profile_path": str(ctx.profile),
        "install_root": str(ctx.install_root),
        "package_file": str(ctx.package_file),
        "bootstrap_log_dir": str(ctx.bootstrap_log_dir),
        "installed_at_epoch": installed_at,
        "previous_adapter_version": previous.get("adapter_version"),
        "files": [{"path": str(path), "sha256": _hash_file(path)} for path in files],
        "server": {"registry_type": DCC_TYPE, "probe_tool": _READINESS_TOOL},
    }


def _readiness_steps(ctx: InstallContext) -> list[dict[str, Any]]:
    return [
        {
            "id": "start_houdini_and_verify",
            "description": "Start the selected Houdini build, then repeat typed verification.",
            "command": _command(ctx, "verify"),
            "why": "Only a live Houdini main-thread probe can prove direct usability.",
        }
    ]


def _verify(ctx: InstallContext, environ: Mapping[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
    for item in receipt.get("files", []):
        path = Path(str(item.get("path", "")))
        if not path.is_file() or _hash_file(path) != item.get("sha256"):
            return {
                "directly_usable": False,
                "failure_stage": "artifact",
                "failure_reason": "Receipted Houdini file is missing or changed: {}".format(path),
            }, []
    try:
        _query_python(ctx.python_path)
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
    entries = [entry for entry in runtime.get("entries", []) if entry.get("mcp_url")]
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
        }, _readiness_steps(ctx)
    ready = wait_for_sidecar_ready(
        environ.get("DCC_MCP_REGISTRY_DIR"),
        dcc_type=DCC_TYPE,
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
        }, _readiness_steps(ctx)
    return {
        "directly_usable": True,
        "failure_stage": None,
        "failure_reason": None,
        "probe_tool": _READINESS_TOOL,
    }, []


def _restore(current: Path, backup: Path) -> None:
    if current.is_dir():
        safe_remove_tree(current)
    elif current.exists():
        current.unlink()
    if backup.exists():
        current.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(backup), str(current))


def _execute_install(ctx: InstallContext, environ: Mapping[str, str]) -> LifecycleOutcome:
    if ctx.state == "partial":
        raise LifecycleFailure("partial", "Unreceipted Houdini package state cannot be overwritten.")
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
    try:
        for relative, content in _expected_sources(ctx).items():
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        expected = _package_payload(ctx.install_root)
        if ctx.install_root.exists():
            backup_root.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(ctx.install_root), str(backup_root))
        if ctx.package_file.is_file():
            backup_package.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(ctx.package_file), str(backup_package))
        if ctx.receipt_path.is_file():
            backup_receipt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(ctx.receipt_path), str(backup_receipt))
        replaced = safe_replace_tree(staged, ctx.install_root)
        if not replaced.get("success"):
            code = INSTALL_EXIT_REQUIRES_RESTART if replaced.get("requires_restart") else INSTALL_EXIT_INSTALL
            raise LifecycleFailure("install", str(replaced.get("message") or "Staged replace failed."), code)
        _write_text_atomic(ctx.package_file, expected)
        _write_json_atomic(ctx.receipt_path, _receipt(ctx, time.time()))
    except BaseException:
        _restore(ctx.install_root, backup_root)
        _restore(ctx.package_file, backup_package)
        _restore(ctx.receipt_path, backup_receipt)
        raise
    finally:
        safe_remove_tree(transaction)

    verify, next_steps = _verify(ctx, environ)
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


def _execute_uninstall(ctx: InstallContext) -> LifecycleOutcome:
    if not ctx.receipt_path.is_file():
        if ctx.install_root.exists() or ctx.package_file.exists():
            raise LifecycleFailure("partial", "Unreceipted Houdini package state cannot be removed safely.")
        result = _base_result(ctx, "ok")
        result["steps"] = [{"id": "uninstall", "status": "already_absent"}]
        return LifecycleOutcome(result, INSTALL_EXIT_OK)
    receipt = _load_json(ctx.receipt_path)
    expected = {ctx.package_file.resolve()}
    expected.update(path.resolve() for path in ctx.install_root.rglob("*") if path.is_file())
    recorded = {Path(str(item.get("path", ""))).resolve() for item in receipt.get("files", [])}
    if recorded != expected:
        raise LifecycleFailure(
            "receipt", "The receipt does not exactly own the Houdini package state.", INSTALL_EXIT_INSTALL
        )
    for item in receipt["files"]:
        path = Path(str(item["path"]))
        if path.exists() and _hash_file(path) != item.get("sha256"):
            raise LifecycleFailure(
                "receipt", "Receipted file was modified and will be preserved: {}".format(path), INSTALL_EXIT_INSTALL
            )
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
    backup_root = transaction / "backup" / _INSTALL_DIR
    backup_package = transaction / "backup" / _PACKAGE_FILE
    backup_receipt = transaction / "backup" / "houdini.json"
    backup_root.parent.mkdir(parents=True, exist_ok=True)
    if ctx.install_root.is_dir():
        shutil.copytree(str(ctx.install_root), str(backup_root))
    shutil.copy2(str(ctx.package_file), str(backup_package))
    shutil.copy2(str(ctx.receipt_path), str(backup_receipt))
    removed = safe_remove_tree(ctx.install_root)
    if not removed.get("success"):
        safe_remove_tree(transaction)
        status = "requires_restart" if removed.get("requires_restart") else "failed"
        result = _base_result(ctx, status)
        result["steps"] = [{"id": "uninstall", "status": status}]
        result["lock"] = removed
        code = INSTALL_EXIT_REQUIRES_RESTART if removed.get("requires_restart") else INSTALL_EXIT_INSTALL
        return LifecycleOutcome(result, code)
    try:
        ctx.package_file.unlink()
        ctx.receipt_path.unlink()
    except BaseException:
        _restore(ctx.install_root, backup_root)
        _restore(ctx.package_file, backup_package)
        _restore(ctx.receipt_path, backup_receipt)
        raise
    finally:
        safe_remove_tree(transaction)
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


def _verify_outcome(ctx: InstallContext, environ: Mapping[str, str]) -> LifecycleOutcome:
    verify, next_steps = _verify(ctx, environ)
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
    retry = [COMMAND, "status", "--json"]
    if dcc_path:
        retry.extend(("--dcc-path", dcc_path))
    if python_path or environ.get(_PYTHON_ENV):
        retry.extend(("--python", python_path or environ[_PYTHON_ENV]))
    packages = environ.get(_PACKAGES_ENV)
    receipt = (
        Path(packages).expanduser().resolve().parent / ".dcc-mcp" / "receipts" / "houdini.json" if packages else None
    )
    result = {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": "requires_restart" if failure.exit_code == INSTALL_EXIT_REQUIRES_RESTART else "failed",
        "dcc_type": DCC_TYPE,
        "adapter_version": __version__,
        "core_version": str(getattr(dcc_mcp_core, "__version__", "unknown")),
        "steps": [{"id": "preflight", "status": "failed", "message": str(failure)}],
        "next_steps": [
            {
                "id": "retry_preflight",
                "description": "Repeat with the exact Houdini host and hython interpreter.",
                "command": retry,
                "why": str(failure),
            }
        ],
        "receipt_path": str(receipt) if receipt else None,
        "verify": {"directly_usable": False, "failure_stage": failure.stage, "failure_reason": str(failure)},
    }
    return LifecycleOutcome(result, failure.exit_code)


def run_lifecycle(
    verb: str,
    *,
    dcc_path: Optional[str],
    python_path: Optional[str],
    yes: bool,
    dry_run: bool,
    environ: Optional[Mapping[str, str]] = None,
) -> LifecycleOutcome:
    """Run one standard lifecycle verb without importing ``hou`` in this process."""
    resolved_environ = os.environ if environ is None else environ
    try:
        ctx = _resolve_context(dcc_path, python_path, resolved_environ)
        if verb == "status":
            return _status(ctx)
        if verb == "verify":
            return _verify_outcome(ctx, resolved_environ)
        if verb == "uninstall":
            return _plan(ctx, verb) if dry_run or not yes else _execute_uninstall(ctx)
        if verb in ("install", "upgrade"):
            if verb == "upgrade" and ctx.state == "fresh":
                raise LifecycleFailure("upgrade", "Nothing is installed; use install for a fresh Houdini profile.")
            return _plan(ctx, verb) if dry_run or not yes else _execute_install(ctx, resolved_environ)
        raise LifecycleFailure("verb", "Unsupported lifecycle verb: {}".format(verb))
    except LifecycleFailure as exc:
        return _failure_result(dcc_path, python_path, resolved_environ, exc)
    except BaseException as exc:
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
