"""Assemble a Houdini quick-install package for dcc-mcp-houdini.

The output ZIP contains:

* the built ``dcc_mcp_houdini`` wheel from ``dist/``;
* compatible ``dcc-mcp-core`` wheels from PyPI for the requested platform;
* a Houdini package JSON template;
* ``scripts/123.py`` and ``scripts/456.py`` autostart hooks;
* ``toolbar/DCC-MCP.shelf`` with basic user-visible controls;
* PowerShell and POSIX installer scripts.

Install flow:

1. Extract the ZIP anywhere stable.
2. Run ``install.ps1 -HoudiniVersion 20.5`` or ``./install.sh 20.5``.
3. Start Houdini. The package adds ``scripts/`` to ``HOUDINI_PATH``; the
   startup hooks extract bundled wheels into ``vendor/`` and start the MCP
   server when ``DCC_MCP_HOUDINI_AUTOSTART`` is not disabled.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import Version

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"
CORE_PACKAGE = "dcc-mcp-core"
MIN_CORE_VERSION = "0.20.14"
PLATFORMS = ("win64", "linux", "macos")
QUICKINSTALL_PYTHON_FLOORS = {"win64": (3, 7), "linux": (3, 7), "macos": (3, 8)}
PYPI_URL = "https://pypi.org/pypi/{package}/json"


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read())


def get_package_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find project version in pyproject.toml")
    return match.group(1)


def _read_assigned_quoted_string(path: Path, key: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^{}\s*=\s*"([^"]+)"'.format(re.escape(key)), text, re.MULTILINE)
    if not match:
        raise RuntimeError('Could not find {} = "..." in {}'.format(key, path))
    return match.group(1)


def assert_versions_aligned() -> None:
    pyproject_version = get_package_version()
    module_version = _read_assigned_quoted_string(
        PACKAGE_ROOT / "src" / "dcc_mcp_houdini" / "__version__.py",
        "__version__",
    )
    if pyproject_version != module_version:
        raise RuntimeError(
            "Version mismatch: pyproject.toml={!r}, __version__.py={!r}".format(
                pyproject_version,
                module_version,
            )
        )


def resolve_core_version(min_version: str = MIN_CORE_VERSION) -> str:
    data = _fetch_json(PYPI_URL.format(package=CORE_PACKAGE))
    available = [Version(v) for v in data["releases"].keys() if not Version(v).is_prerelease]
    compatible = [
        v
        for v in available
        if v >= Version(min_version)
        and v < Version("1.0.0")
        and all(
            any(
                _wheel_has_abi3(str(item.get("filename", "")))
                for item in pick_core_wheel_files(data["releases"][str(v)], platform)
            )
            and bool(
                pick_core_wheel_files(
                    data["releases"][str(v)],
                    platform,
                    python_version=QUICKINSTALL_PYTHON_FLOORS[platform],
                )
            )
            for platform in PLATFORMS
        )
    ]
    if not compatible:
        raise RuntimeError(
            "No compatible {} release found >= {} with abi3 wheels for {}".format(
                CORE_PACKAGE,
                min_version,
                ", ".join(PLATFORMS),
            )
        )
    return str(sorted(compatible)[-1])


def validate_core_version(version: str, min_version: str = MIN_CORE_VERSION) -> str:
    parsed = Version(version)
    if parsed.is_prerelease or parsed < Version(min_version) or parsed >= Version("1.0.0"):
        raise RuntimeError(
            "Requested {} version {!r} is outside the supported range >= {},<1.0.0".format(
                CORE_PACKAGE,
                version,
                min_version,
            )
        )
    return str(parsed)


def select_core_version(core_version: Optional[str] = None) -> str:
    if core_version:
        return validate_core_version(core_version)
    return resolve_core_version()


def _platform_tag_matches_target(platform_tag: str, target: str) -> bool:
    if target == "win64":
        return platform_tag == "win_amd64"
    if target == "linux":
        return (
            re.fullmatch(
                r"(?:linux|manylinux(?:_[0-9]+_[0-9]+|[0-9]{4}))_(?:x86_64|aarch64)",
                platform_tag,
            )
            is not None
        )
    if target == "macos":
        return re.fullmatch(r"macosx_[0-9]+_[0-9]+_(?:x86_64|arm64|universal2)", platform_tag) is not None
    return False


def _wheel_matches_platform(filename: str, platform: str) -> bool:
    try:
        _name, _version, _build, tags = parse_wheel_filename(filename)
    except InvalidWheelFilename:
        return False
    return any(_platform_tag_matches_target(tag.platform, platform) for tag in tags)


def _wheel_rank(filename: str) -> tuple:
    if "cp38-abi3" in filename:
        priority = 0
    elif "abi3" in filename:
        priority = 1
    elif "cp313" in filename:
        priority = 2
    elif "cp312" in filename:
        priority = 3
    elif "cp311" in filename:
        priority = 4
    elif "cp310" in filename:
        priority = 5
    elif "cp39" in filename:
        priority = 6
    elif "cp38" in filename:
        priority = 7
    elif "cp37" in filename:
        priority = 8
    else:
        priority = 50
    return (priority, filename)


def _interpreter_version(interpreter: str) -> Optional[Tuple[int, int]]:
    match = re.fullmatch(r"cp(?P<major>[0-9])(?P<minor>[0-9]+)", interpreter)
    if not match:
        return None
    version = int(match.group("major")), int(match.group("minor"))
    return version if version[0] == 3 and version >= (3, 7) else None


def _abi_matches_interpreter(interpreter: str, abi: str) -> bool:
    version = _interpreter_version(interpreter)
    if version is None:
        return False
    if abi == "abi3":
        return version >= (3, 8)
    expected = interpreter + "m" if version <= (3, 7) else interpreter
    return abi == expected


def _wheel_has_supported_native_abi(filename: str) -> bool:
    try:
        _name, _version, _build, tags = parse_wheel_filename(filename)
    except InvalidWheelFilename:
        return False
    return bool(tags) and all(tag.abi != "none" and _abi_matches_interpreter(tag.interpreter, tag.abi) for tag in tags)


def _wheel_has_abi3(filename: str) -> bool:
    try:
        _name, _version, _build, tags = parse_wheel_filename(filename)
    except InvalidWheelFilename:
        return False
    return any(tag.abi == "abi3" for tag in tags)


def _wheel_supports_python(filename: str, python_version: Tuple[int, int]) -> bool:
    try:
        _name, _version, _build, tags = parse_wheel_filename(filename)
    except InvalidWheelFilename:
        return False
    runtime_major = python_version[0]
    for tag in tags:
        tag_version = _interpreter_version(tag.interpreter)
        if tag_version is None or not _abi_matches_interpreter(tag.interpreter, tag.abi):
            continue
        if tag.abi == "abi3" and runtime_major == tag_version[0] and python_version >= tag_version:
            return True
        if python_version == tag_version:
            return True
    return False


def pick_core_wheel_files(
    release_files: List[Dict[str, object]],
    platform: str,
    python_version: Optional[Tuple[int, int]] = None,
) -> List[Dict[str, object]]:
    candidates = [
        f
        for f in release_files
        if _wheel_matches_platform(str(f.get("filename", "")), platform)
        and _wheel_has_supported_native_abi(str(f.get("filename", "")))
    ]
    if python_version is not None:
        candidates = [f for f in candidates if _wheel_supports_python(str(f.get("filename", "")), python_version)]
    candidates.sort(key=lambda f: _wheel_rank(str(f["filename"])))
    return candidates


def download_core_wheels(version: str, platform: str, dest_dir: Path) -> List[Path]:
    data = _fetch_json(PYPI_URL.format(package=CORE_PACKAGE))
    release_files = data["releases"].get(version, [])
    picks = pick_core_wheel_files(release_files, platform)
    if not picks:
        sample = [str(f["filename"]) for f in release_files if str(f.get("filename", "")).endswith(".whl")][:12]
        raise RuntimeError(
            "No {} wheel for platform={!r} at version {!r}. Wheel sample: {}".format(
                CORE_PACKAGE,
                platform,
                version,
                sample,
            )
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for pick in picks:
        filename = str(pick["filename"])
        dest = dest_dir / filename
        if not dest.exists():
            urllib.request.urlretrieve(str(pick["url"]), dest)  # noqa: S310
        paths.append(dest)
    return paths


def _wheel_version(filename: str, distribution: str) -> Optional[str]:
    match = re.match(r"^{}-(?P<version>[^-]+)-.+\.whl$".format(re.escape(distribution)), filename)
    if not match:
        return None
    return match.group("version")


def find_adapter_wheel(dist_dir: Path, version: str) -> Path:
    wheels = sorted(dist_dir.glob("dcc_mcp_houdini-{}-*.whl".format(version)))
    if not wheels:
        raise RuntimeError("Adapter wheel not found in {} for version {}".format(dist_dir, version))
    return wheels[-1]


def _package_json_template() -> str:
    payload = {
        "env": [
            {"DCC_MCP_HOUDINI_ROOT": "__PACKAGE_ROOT__"},
            {"PYTHONPATH": "__PACKAGE_ROOT__/vendor;&"},
            {"HOUDINI_PATH": "__PACKAGE_ROOT__;&"},
        ]
    }
    return json.dumps(payload, indent=2) + "\n"


def _bootstrap_py(expected_adapter_version: Optional[str] = None) -> str:
    if expected_adapter_version is None:
        expected_adapter_version = get_package_version()
    source = r'''"""Bootstrap bundled dcc-mcp-houdini wheels inside Houdini."""

from __future__ import annotations

import importlib
import importlib.util
from contextlib import contextmanager
from email.parser import Parser
import json
import os
import platform
from pathlib import Path
import re
import shutil
import sys
import time
import uuid
import zipfile

_EXPECTED_ADAPTER_VERSION = __DCC_MCP_EXPECTED_ADAPTER_VERSION__
_EXPECTED_ADAPTER_DISTRIBUTION = "dcc_mcp_houdini"


def _package_root() -> Path:
    env_root = os.environ.get("DCC_MCP_HOUDINI_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _wheel_marker(wheels) -> str:
    return "\n".join(sorted("{}:{}".format(w.name, w.stat().st_size) for w in wheels))


def _wheel_tags(wheel: Path):
    parts = wheel.name[:-4].rsplit("-", 3) if wheel.name.endswith(".whl") else []
    if len(parts) != 4:
        return None
    return parts[1], parts[2], parts[3]


def _normalized_machine(machine: str):
    return {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine.lower())


def _interpreter_version(interpreter: str):
    match = re.fullmatch(r"cp([0-9])([0-9]+)", interpreter)
    if not match:
        return None
    version = int(match.group(1)), int(match.group(2))
    return version if version[0] == 3 and version >= (3, 7) else None


def _abi_matches_interpreter(interpreter: str, abi: str) -> bool:
    version = _interpreter_version(interpreter)
    if version is None:
        return False
    if abi == "abi3":
        return version >= (3, 8)
    expected = interpreter + "m" if version <= (3, 7) else interpreter
    return abi == expected


def _wheel_has_supported_native_abi(wheel: Path) -> bool:
    tags = _wheel_tags(wheel)
    if tags is None:
        return False
    python_tag, abi_tag, platform_tag = tags
    interpreters = python_tag.split(".")
    abis = abi_tag.split(".")
    return (
        bool(interpreters and abis)
        and all(
            _abi_matches_interpreter(interpreter, abi)
            for interpreter in interpreters
            for abi in abis
        )
        and _platform_tag_is_supported(platform_tag)
    )


def _platform_tag_is_supported(platform_tag: str) -> bool:
    tags = platform_tag.split(".")
    return bool(tags) and all(
        tag == "win_amd64"
        or re.fullmatch(r"macosx_[0-9]+_[0-9]+_(x86_64|arm64|universal2)", tag)
        is not None
        or re.fullmatch(
            r"(?:linux|manylinux(?:_[0-9]+_[0-9]+|[0-9]{4}))_(x86_64|aarch64)",
            tag,
        )
        is not None
        for tag in tags
    )


def _platform_tag_matches_runtime(platform_tag: str, platform_name: str, machine: str) -> bool:
    normalized_machine = _normalized_machine(machine)
    if normalized_machine is None:
        return False
    for tag in platform_tag.split("."):
        if platform_name == "darwin":
            match = re.fullmatch(r"macosx_[0-9]+_[0-9]+_(x86_64|arm64|universal2)", tag)
            if match and (match.group(1) == normalized_machine or match.group(1) == "universal2"):
                return True
        elif platform_name.startswith("win"):
            if normalized_machine == "x86_64" and tag == "win_amd64":
                return True
        elif platform_name.startswith("linux"):
            match = re.fullmatch(
                r"(?:linux|manylinux(?:_[0-9]+_[0-9]+|[0-9]{4}))_(x86_64|aarch64)",
                tag,
            )
            expected_arch = "x86_64" if normalized_machine == "x86_64" else "aarch64"
            if match and match.group(1) == expected_arch:
                return True
    return False


def _native_wheel_supports_runtime(wheel: Path, python_version, platform_name: str, machine: str) -> bool:
    tags = _wheel_tags(wheel)
    if tags is None or not _wheel_has_supported_native_abi(wheel):
        return False
    python_tag, abi_tag, platform_tag = tags
    if not _platform_tag_matches_runtime(platform_tag, platform_name, machine):
        return False
    runtime = tuple(int(part) for part in python_version[:2])
    for interpreter in python_tag.split("."):
        minimum = _interpreter_version(interpreter)
        if minimum is None:
            continue
        abis = abi_tag.split(".")
        if "abi3" in abis and runtime[0] == minimum[0] and runtime >= minimum:
            return True
        if runtime == minimum and any(
            _abi_matches_interpreter(interpreter, abi) for abi in abis
        ):
            return True
    return False


def _require_compatible_core_wheel(
    wheels,
    python_version=None,
    platform_name=None,
    machine=None,
):
    python_version = tuple(python_version or sys.version_info[:2])
    platform_name = platform_name or sys.platform
    machine = machine or platform.machine()
    core_wheels = [wheel for wheel in wheels if wheel.name.startswith("dcc_mcp_core-")]
    unsupported = [wheel for wheel in core_wheels if not _wheel_has_supported_native_abi(wheel)]
    if unsupported:
        raise RuntimeError(
            "Bundled Core wheels contain unsupported interpreter/ABI or platform tags: {}".format(
                ", ".join(wheel.name for wheel in unsupported)
            )
        )
    compatible = [
        wheel
        for wheel in core_wheels
        if _native_wheel_supports_runtime(wheel, python_version, platform_name, machine)
    ]
    if len(compatible) == 1:
        return compatible
    if len(compatible) > 1:
        raise RuntimeError(
            "Multiple bundled Core wheels match this runtime; refusing ambiguous extraction: {}".format(
                ", ".join(wheel.name for wheel in compatible)
            )
        )
    label = "macOS" if platform_name == "darwin" else platform_name
    floor = "3.8" if platform_name == "darwin" else "3.7"
    raise RuntimeError(
        "Bundled Core native wheels for {} require Python {} or newer; "
        "no wheel matches Python {}.{}.".format(label, floor, python_version[0], python_version[1])
    )


def _windows_component_key(component: str) -> str:
    sanitized = re.sub(r'[<>:"|?*]', "_", component).rstrip(" .")
    if not sanitized:
        raise RuntimeError("unsafe wheel member component")
    device_stem = sanitized.split(".", 1)[0].rstrip(" .").casefold()
    if device_stem in {"con", "prn", "aux", "nul"} or re.fullmatch(
        r"(?:com|lpt)[1-9]", device_stem
    ):
        raise RuntimeError("unsafe wheel member component")
    return sanitized.casefold()


def _portable_member_key(parts) -> str:
    return "/".join(_windows_component_key(part) for part in parts)


def _validate_wheel_members(wheels) -> None:
    members = {}
    for wheel in wheels:
        with zipfile.ZipFile(str(wheel), "r") as archive:
            for info in archive.infolist():
                raw_name = info.filename.replace("\\", "/")
                trimmed = raw_name.rstrip("/")
                if not trimmed:
                    continue
                parts = trimmed.split("/")
                if (
                    raw_name.startswith("/")
                    or any(part in ("", ".", "..") for part in parts)
                    or ":" in parts[0]
                ):
                    raise RuntimeError(
                        "unsafe wheel member in {}: {}".format(wheel.name, info.filename)
                    )
                try:
                    normalized = _portable_member_key(parts)
                except RuntimeError as exc:
                    raise RuntimeError(
                        "unsafe wheel member in {}: {}".format(wheel.name, info.filename)
                    ) from exc
                if normalized == ".dcc_mcp_houdini_wheels":
                    raise RuntimeError(
                        "wheel member collides with the managed vendor marker: {}".format(
                            wheel.name
                        )
                    )
                is_directory = info.is_dir() or raw_name.endswith("/")
                previous = members.get(normalized)
                if previous is not None and (not is_directory or not previous[1]):
                    raise RuntimeError(
                        "overlapping wheel member {} in {} and {}".format(
                            info.filename,
                            previous[0],
                            wheel.name,
                        )
                    )
                if previous is None:
                    members[normalized] = (wheel.name, is_directory)

    all_members = sorted(members)
    file_members = sorted(member for member, (_wheel, is_directory) in members.items() if not is_directory)
    for member in file_members:
        prefix = member + "/"
        if any(candidate.startswith(prefix) for candidate in all_members):
            raise RuntimeError("overlapping wheel member path: {}".format(member))


def _validate_adapter_wheel_identity(wheel: Path) -> None:
    expected_name = "{}-{}-py3-none-any.whl".format(
        _EXPECTED_ADAPTER_DISTRIBUTION,
        _EXPECTED_ADAPTER_VERSION,
    )
    expected_dist_info = "{}-{}.dist-info".format(
        _EXPECTED_ADAPTER_DISTRIBUTION,
        _EXPECTED_ADAPTER_VERSION,
    )
    if wheel.name != expected_name:
        raise RuntimeError(
            "Invalid vendor wheel set; adapter wheel identity does not match the packaged adapter"
        )
    with zipfile.ZipFile(str(wheel), "r") as archive:
        infos = archive.infolist()
        dist_infos = sorted(
            {
                info.filename.replace("\\", "/").strip("/").split("/", 1)[0]
                for info in infos
                if ".dist-info/" in info.filename.replace("\\", "/")
            }
        )
        metadata_infos = [
            info for info in infos if info.filename == expected_dist_info + "/METADATA"
        ]
        try:
            metadata = (
                Parser().parsestr(archive.read(metadata_infos[0]).decode("utf-8"))
                if len(metadata_infos) == 1
                else None
            )
        except (KeyError, UnicodeDecodeError):
            metadata = None
    normalized_metadata_name = re.sub(
        r"[-_.]+",
        "_",
        metadata.get("Name", "") if metadata is not None else "",
    ).casefold()
    metadata_version = metadata.get("Version") if metadata is not None else None
    if (
        dist_infos != [expected_dist_info]
        or normalized_metadata_name != _EXPECTED_ADAPTER_DISTRIBUTION
        or metadata_version != _EXPECTED_ADAPTER_VERSION
    ):
        raise RuntimeError(
            "Invalid vendor wheel set; adapter wheel identity does not match its dist-info"
        )


def _select_vendor_wheels(wheels):
    selected_core_wheels = _require_compatible_core_wheel(wheels)
    expected_adapter_name = "{}-{}-py3-none-any.whl".format(
        _EXPECTED_ADAPTER_DISTRIBUTION,
        _EXPECTED_ADAPTER_VERSION,
    )
    adapter_candidates = [
        wheel for wheel in wheels if wheel.name.startswith(_EXPECTED_ADAPTER_DISTRIBUTION)
    ]
    adapter_wheels = [wheel for wheel in adapter_candidates if wheel.name == expected_adapter_name]
    unexpected = [
        wheel
        for wheel in wheels
        if not wheel.name.startswith("dcc_mcp_core-")
        and wheel not in adapter_wheels
    ]
    if unexpected or len(adapter_candidates) != 1 or len(adapter_wheels) != 1:
        raise RuntimeError(
            "Invalid vendor wheel set; adapter wheel identity must match the packaged adapter: {}".format(
                ", ".join(wheel.name for wheel in wheels)
            )
        )
    _validate_adapter_wheel_identity(adapter_wheels[0])
    return sorted(adapter_wheels + selected_core_wheels)


@contextmanager
def _capture_early_bootstrap_errors(root: Path):
    try:
        yield
    except Exception as exc:
        log_dir = root / ".dcc-mcp/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp_epoch": time.time(),
            "dcc_type": "houdini",
            "phase": "vendor-bootstrap",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        (log_dir / "houdini-bootstrap-early.host-errors.log").write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise


def _load_install_lifecycle(vendor_dir: Path):
    helper = vendor_dir / "dcc_mcp_core/install_lifecycle.py"
    if not helper.is_file():
        raise RuntimeError(
            "Existing vendor has no Core install_lifecycle helper; "
            "close Houdini and reinstall the quickinstall package"
        )
    vendor_str = str(vendor_dir)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)
    importlib.invalidate_caches()
    module = importlib.import_module("dcc_mcp_core.install_lifecycle")
    loaded_from = Path(module.__file__).resolve()
    if vendor_dir.resolve() not in loaded_from.parents:
        raise RuntimeError("Core install lifecycle resolved outside the managed vendor: {}".format(loaded_from))
    return module


def ensure_vendor(root: Path) -> Path:
    wheels_dir = root / "wheels"
    vendor_dir = root / "vendor"
    wheels = sorted(wheels_dir.glob("*.whl"))
    if not wheels:
        raise RuntimeError("No bundled wheels found under {}".format(wheels_dir))
    selected_wheels = _select_vendor_wheels(wheels)
    _validate_wheel_members(selected_wheels)
    marker = vendor_dir / ".dcc_mcp_houdini_wheels"
    desired = _wheel_marker(selected_wheels)
    if marker.is_file() and marker.read_text(encoding="utf-8") == desired:
        return vendor_dir
    token = uuid.uuid4().hex
    stage = root / (".vendor-stage-" + token)
    backup = root / (".vendor-backup-" + token)
    try:
        stage.mkdir(parents=True)
        for wheel in selected_wheels:
            with zipfile.ZipFile(str(wheel), "r") as zf:
                zf.extractall(str(stage))
        (stage / ".dcc_mcp_houdini_wheels").write_text(desired, encoding="utf-8")
        if not vendor_dir.exists():
            os.replace(str(stage), str(vendor_dir))
            return vendor_dir

        lifecycle = _load_install_lifecycle(vendor_dir)
        inspection = lifecycle.inspect_install_root(vendor_dir)
        if inspection.get("requires_restart"):
            raise RuntimeError(
                "requires_restart: close Houdini before replacing loaded vendor artifact {}".format(
                    inspection.get("locked_path")
                )
            )
        os.replace(str(vendor_dir), str(backup))
        replaced = lifecycle.safe_replace_tree(stage, vendor_dir)
        if not replaced.get("success"):
            os.replace(str(backup), str(vendor_dir))
            raise RuntimeError(replaced.get("message") or "Core staged vendor replace failed")
        lifecycle.safe_remove_tree(stage)
        cleanup = lifecycle.safe_remove_tree(backup)
        if not cleanup.get("success"):
            print("dcc-mcp-houdini: previous vendor cleanup deferred: {}".format(cleanup))
        return vendor_dir
    except Exception:
        if stage.exists():
            shutil.rmtree(str(stage), ignore_errors=True)
        if backup.exists() and not vendor_dir.exists():
            os.replace(str(backup), str(vendor_dir))
        raise


def bootstrap_and_start() -> object:
    if os.environ.get("DCC_MCP_BACKGROUND_RENDER") == "1":
        return None
    root = _package_root()
    with _capture_early_bootstrap_errors(root):
        vendor = ensure_vendor(root)
    vendor_str = str(vendor)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)
    importlib.invalidate_caches()

    try:
        from dcc_mcp_core import capture_bootstrap_errors
    except ImportError:
        # Preserve compatibility with minimal development wheels. Release
        # quickinstalls always bundle Core and therefore use real capture.
        @contextmanager
        def capture_bootstrap_errors(*_args, **_kwargs):
            yield

    with capture_bootstrap_errors(
        "houdini",
        min_core_version="0.20.14",
        phase="quickinstall-bootstrap",
        log_dir=str(root / ".dcc-mcp/logs"),
    ):
        if os.environ.get("DCC_MCP_HOUDINI_AUTOSTART", "1").strip().lower() in {"0", "false", "no", "off"}:
            return None

        import dcc_mcp_houdini

        try:
            import hou

            if not hou.isUIAvailable():
                print(
                    "dcc-mcp-houdini: headless startup hook skipped; "
                    "run `hython -m dcc_mcp_houdini` for the foreground main-thread pump"
                )
                return None
        except ImportError:
            pass

        gateway_raw = os.environ.get("DCC_MCP_GATEWAY_PORT")
        gateway_port = int(gateway_raw) if gateway_raw and gateway_raw.isdigit() else None
        registry_dir = os.environ.get("DCC_MCP_REGISTRY_DIR") or None
        return dcc_mcp_houdini.start_server(
            gateway_port=gateway_port,
            registry_dir=registry_dir,
            wait_ready=False,
        )
'''
    return source.replace(
        "__DCC_MCP_EXPECTED_ADAPTER_VERSION__",
        repr(str(expected_adapter_version)),
    )


def _startup_py() -> str:
    return r'''"""Houdini autostart hook for dcc-mcp-houdini."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _load_bootstrap():
    root = os.environ.get("DCC_MCP_HOUDINI_ROOT")
    script = globals().get("__file__")
    if root:
        path = Path(root) / "scripts/dcc_mcp_houdini_bootstrap.py"
    elif script:
        path = Path(script).with_name("dcc_mcp_houdini_bootstrap.py")
    else:
        raise RuntimeError("DCC_MCP_HOUDINI_ROOT is not set")
    spec = importlib.util.spec_from_file_location("dcc_mcp_houdini_bootstrap", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load {}".format(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    bootstrap = _load_bootstrap()
    try:
        from dcc_mcp_core import capture_bootstrap_errors
    except ImportError:
        server = bootstrap.bootstrap_and_start()
    else:
        root = os.environ.get("DCC_MCP_HOUDINI_ROOT")
        log_dir = str(Path(root) / ".dcc-mcp/logs") if root else None
        with capture_bootstrap_errors(
            "houdini",
            min_core_version="0.20.14",
            phase="startup-hook",
            log_dir=log_dir,
        ):
            server = bootstrap.bootstrap_and_start()
    if server is not None:
        print("dcc-mcp-houdini MCP server started: {}".format(server.mcp_url))
except Exception as exc:
    print("dcc-mcp-houdini autostart failed: {}".format(exc))
'''


def _shelf_file() -> str:
    return r"""<?xml version="1.0" encoding="UTF-8"?>
<shelfDocument>
  <toolshelf name="DCC-MCP" label="DCC-MCP">
    <memberTool name="dcc_mcp_houdini_copy_id"/>
    <memberTool name="dcc_mcp_houdini_server_info"/>
    <memberTool name="dcc_mcp_houdini_about"/>
    <memberTool name="dcc_mcp_houdini_start"/>
    <memberTool name="dcc_mcp_houdini_stop"/>
  </toolshelf>
  <tool name="dcc_mcp_houdini_copy_id" label="Copy Instance ID" icon="BUTTONS_info" helpText="Copy the DCC-MCP instance UUID to the clipboard.">
    <script scriptType="python"><![CDATA[
try:
    import dcc_mcp_houdini
    server = dcc_mcp_houdini.get_server()
except Exception:
    server = None

instance_id = None
if server is not None:
    for attr in ("instance_id", "_config"):
        val = getattr(server, attr, None)
        if isinstance(val, str):
            instance_id = val
            break
        if hasattr(val, "instance_id"):
            instance_id = getattr(val, "instance_id", None)
            if isinstance(instance_id, str):
                break
    if instance_id is None:
        instance_id = getattr(server, "instance_id", None) or "unknown"

copied = False
try:
    from PySide2.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        clipboard = app.clipboard()
        if clipboard is not None:
            clipboard.setText(str(instance_id))
            copied = True
except Exception:
    pass
# Fallback: copy to stdout for headless / non-Qt sessions
if not copied:
    print("Instance ID: {}".format(instance_id))

message = "Instance ID copied: {}".format(instance_id) if copied else "Instance ID: {}".format(instance_id)
try:
    import hou
    hou.ui.setStatusMessage(message)
except Exception:
    print(message)
]]></script>
  </tool>
  <tool name="dcc_mcp_houdini_server_info" label="Server Info" icon="BUTTONS_info" helpText="Show DCC-MCP Houdini server information.">
    <script scriptType="python"><![CDATA[
try:
    import dcc_mcp_houdini
    server = dcc_mcp_houdini.get_server()
except Exception:
    server = None

if server is not None and getattr(server, "is_running", False):
    instance_id = None
    for attr in ("instance_id", "_config"):
        val = getattr(server, attr, None)
        if isinstance(val, str):
            instance_id = val
            break
        if hasattr(val, "instance_id"):
            instance_id = getattr(val, "instance_id", None)
            if isinstance(instance_id, str):
                break
    if instance_id is None:
        instance_id = getattr(server, "instance_id", None) or "unknown"

    try:
        from dcc_mcp_houdini import __version__ as adapter_version
    except Exception:
        adapter_version = "unknown"

    try:
        from dcc_mcp_houdini._version_probe import get_houdini_version_string
        houdini_version = get_houdini_version_string()
    except Exception:
        houdini_version = "unknown"

    lines = [
        "DCC-MCP Houdini Server Info",
        "  MCP URL:       {}".format(server.mcp_url),
        "  Instance UUID: {}".format(instance_id),
        "  Adapter:       dcc-mcp-houdini {}".format(adapter_version),
        "  Houdini:       {}".format(houdini_version),
        "  Port:          {}".format(server.port),
    ]
    info = "\n".join(lines)
else:
    info = "DCC-MCP Houdini server is not running."

try:
    import hou
    hou.ui.displayMessage(info, title="DCC-MCP Houdini Server Info")
except Exception:
    print(info)
]]></script>
  </tool>
  <tool name="dcc_mcp_houdini_about" label="About DCC MCP" icon="BUTTONS_help" helpText="About DCC-MCP Houdini.">
    <script scriptType="python"><![CDATA[
try:
    from dcc_mcp_houdini import __version__ as adapter_version
except Exception:
    adapter_version = "unknown"

try:
    from dcc_mcp_houdini._version_probe import get_houdini_version_string
    houdini_version = get_houdini_version_string()
except Exception:
    houdini_version = "unknown"

about = (
    "DCC-MCP Houdini v{}\n"
    "Houdini {}\n\n"
    "GitHub: https://github.com/dcc-mcp/dcc-mcp-houdini\n"
    "Docs:   https://github.com/dcc-mcp/dcc-mcp-houdini#readme"
).format(adapter_version, houdini_version)

try:
    import hou
    hou.ui.displayMessage(about, title="About DCC-MCP Houdini")
except Exception:
    print(about)
]]></script>
  </tool>
  <tool name="dcc_mcp_houdini_start" label="Start MCP" icon="MISC_python" helpText="Start the DCC-MCP Houdini server.">
    <script scriptType="python"><![CDATA[
try:
    import dcc_mcp_houdini

    server = dcc_mcp_houdini.start_server(wait_ready=False)
    message = "DCC-MCP Houdini server: {}".format(server.mcp_url)
except Exception as exc:
    message = "DCC-MCP Houdini start failed: {}".format(exc)

try:
    import hou

    hou.ui.setStatusMessage(message)
except Exception:
    print(message)
]]></script>
  </tool>
  <tool name="dcc_mcp_houdini_stop" label="Stop MCP" icon="MISC_python" helpText="Stop the DCC-MCP Houdini server.">
    <script scriptType="python"><![CDATA[
try:
    import dcc_mcp_houdini

    dcc_mcp_houdini.stop_server()
    message = "DCC-MCP Houdini server stopped."
except Exception as exc:
    message = "DCC-MCP Houdini stop failed: {}".format(exc)

try:
    import hou

    hou.ui.setStatusMessage(message)
except Exception:
    print(message)
]]></script>
  </tool>
</shelfDocument>
"""


def _install_ps1() -> str:
    return r"""param(
  [string]$HoudiniVersion = "20.5",
  [string]$PackageRoot = $PSScriptRoot,
  [string]$PackagesDir = ""
)

$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path -LiteralPath $PackageRoot).Path.Replace("\", "/")
$packagesDirOverride = $PackagesDir
if ([string]::IsNullOrWhiteSpace($packagesDirOverride)) {
  $packagesDirOverride = $env:DCC_MCP_HOUDINI_PACKAGES_DIR
}
if ([string]::IsNullOrWhiteSpace($packagesDirOverride)) {
  $resolvedPackagesDir = Join-Path $HOME "Documents/houdini$HoudiniVersion/packages"
} else {
  $resolvedPackagesDir = [IO.Path]::GetFullPath($packagesDirOverride)
}
New-Item -ItemType Directory -Force -Path $resolvedPackagesDir | Out-Null

$template = Get-Content -LiteralPath (Join-Path $PSScriptRoot "packages/dcc_mcp_houdini.json.template") -Raw
$json = $template.Replace("__PACKAGE_ROOT__", $resolvedRoot)
$target = Join-Path $resolvedPackagesDir "dcc_mcp_houdini.json"
[IO.File]::WriteAllText($target, $json, [Text.UTF8Encoding]::new($false))

Write-Host "Installed Houdini package: $target"
Write-Host "Package root: $resolvedRoot"
Write-Host "Start Houdini $HoudiniVersion; connect through the gateway at http://127.0.0.1:9765/mcp"
"""


def _install_sh() -> str:
    return r"""#!/usr/bin/env sh
set -eu

HOUDINI_VERSION="${1:-20.5}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PACKAGE_ROOT="${PACKAGE_ROOT:-$SCRIPT_DIR}"
if [ -n "${DCC_MCP_HOUDINI_PACKAGES_DIR:-}" ]; then
  PACKAGES_DIR="$DCC_MCP_HOUDINI_PACKAGES_DIR"
elif [ "$(uname -s)" = "Darwin" ]; then
  PACKAGES_DIR="$HOME/Library/Preferences/houdini/$HOUDINI_VERSION/packages"
else
  PACKAGES_DIR="$HOME/houdini$HOUDINI_VERSION/packages"
fi

mkdir -p "$PACKAGES_DIR"
ROOT_ESCAPED="$(cd "$PACKAGE_ROOT" && pwd)"
sed "s#__PACKAGE_ROOT__#$ROOT_ESCAPED#g" \
  "$SCRIPT_DIR/packages/dcc_mcp_houdini.json.template" \
  > "$PACKAGES_DIR/dcc_mcp_houdini.json"

echo "Installed Houdini package: $PACKAGES_DIR/dcc_mcp_houdini.json"
echo "Package root: $ROOT_ESCAPED"
echo "Start Houdini $HOUDINI_VERSION; connect through the gateway at http://127.0.0.1:9765/mcp"
"""


def _readme(version: str, core_version: str, platform: str, explicit_core_version: bool = False) -> str:
    if explicit_core_version:
        core_policy = "explicit validated dcc-mcp-core {}.".format(core_version)
    else:
        core_policy = (
            "latest non-prerelease dcc-mcp-core >= {},<1.0.0 with abi3 wheels "
            "for every release platform at assembly time."
        ).format(MIN_CORE_VERSION)
    python_floor = ".".join(str(part) for part in QUICKINSTALL_PYTHON_FLOORS[platform])
    return """dcc-mcp-houdini quick install package
======================================

Version: {version}
dcc-mcp-core wheels: {core_version}
Platform: {platform}
Core bundle policy: {core_policy}
Bundled Core Python compatibility: {python_floor} or newer on {platform}.
Old-core pin: none.

Install on Windows:
  powershell -ExecutionPolicy Bypass -File install.ps1 -HoudiniVersion 20.5
  # Optional isolated/custom target: -PackagesDir C:\\path\\to\\houdini-packages

Install on Linux/macOS:
  chmod +x install.sh
  ./install.sh 20.5

Set DCC_MCP_HOUDINI_PACKAGES_DIR to override the target package directory.
On Windows, -PackagesDir takes precedence over the environment variable.

The installer writes a Houdini package JSON into the user Houdini preferences
folder and points it at this extracted package directory. On Houdini startup,
scripts/123.py handles empty startup and scripts/456.py handles loaded scenes;
both reuse the same bootstrap to extract bundled wheels and start the MCP server.
The DCC-MCP shelf is loaded from toolbar/DCC-MCP.shelf.

Disable autostart by setting DCC_MCP_HOUDINI_AUTOSTART=0.
Background render children set DCC_MCP_BACKGROUND_RENDER=1; startup hooks must
not start another MCP adapter when this child-only marker is present.
Instance ports are assigned by the operating system. Connect through the stable
gateway at http://127.0.0.1:9765/mcp or discover exact URLs with dcc-mcp-cli.
""".format(
        version=version,
        core_version=core_version,
        platform=platform,
        core_policy=core_policy,
        python_floor=python_floor,
    )


def verify_quickinstall_zip(
    zip_path: Path,
    platform: str,
    expected_core_version: Optional[str] = None,
) -> Dict[str, object]:
    if platform not in PLATFORMS:
        raise ValueError("Unsupported platform {!r}; expected {}".format(platform, ", ".join(PLATFORMS)))
    if expected_core_version is None:
        expected_core_version = select_core_version()
    else:
        expected_core_version = validate_core_version(expected_core_version)

    adapter_version = get_package_version()
    with zipfile.ZipFile(str(zip_path)) as zf:
        names = zf.namelist()

    required_suffixes = [
        "/scripts/123.py",
        "/scripts/456.py",
        "/scripts/dcc_mcp_houdini_bootstrap.py",
        "/packages/dcc_mcp_houdini.json.template",
        "/README.txt",
    ]
    for suffix in required_suffixes:
        if not any(name.endswith(suffix) for name in names):
            raise RuntimeError("quickinstall zip missing {}".format(suffix))

    wheel_names = [Path(name).name for name in names if "/wheels/" in name and name.endswith(".whl")]
    adapter_wheels = [name for name in wheel_names if _wheel_version(name, "dcc_mcp_houdini")]
    core_wheels = [name for name in wheel_names if _wheel_version(name, "dcc_mcp_core")]
    if not adapter_wheels:
        raise RuntimeError("quickinstall zip missing dcc-mcp-houdini wheel")
    if not core_wheels:
        raise RuntimeError("quickinstall zip missing dcc-mcp-core wheel")

    adapter_versions = sorted({str(_wheel_version(name, "dcc_mcp_houdini")) for name in adapter_wheels})
    core_versions = sorted({str(_wheel_version(name, "dcc_mcp_core")) for name in core_wheels})
    expected_adapter = "dcc_mcp_houdini-{}-py3-none-any.whl".format(adapter_version)
    unexpected_wheels = [
        name
        for name in wheel_names
        if not _wheel_version(name, "dcc_mcp_houdini") and not _wheel_version(name, "dcc_mcp_core")
    ]
    if adapter_wheels != [expected_adapter] or unexpected_wheels:
        raise RuntimeError(
            "Invalid vendor wheel set; expected one adapter and Core wheels only: {}".format(", ".join(wheel_names))
        )
    if adapter_versions != [adapter_version]:
        raise RuntimeError(
            "Adapter wheel drift: expected dcc-mcp-houdini {}, found {}".format(
                adapter_version,
                ", ".join(adapter_versions),
            )
        )
    if core_versions != [expected_core_version]:
        raise RuntimeError(
            "Bundled core drift: expected dcc-mcp-core {}, found {}".format(
                expected_core_version,
                ", ".join(core_versions),
            )
        )

    wrong_platform = [name for name in core_wheels if not _wheel_matches_platform(name, platform)]
    if wrong_platform:
        raise RuntimeError("Core wheels do not match platform {}: {}".format(platform, ", ".join(wrong_platform)))
    unsupported_abi = [name for name in core_wheels if not _wheel_has_supported_native_abi(name)]
    if unsupported_abi:
        raise RuntimeError(
            "Core wheels contain unsupported interpreter/ABI tags: {}".format(", ".join(unsupported_abi))
        )
    if not any(_wheel_has_abi3(name) for name in core_wheels):
        raise RuntimeError(
            "Core wheels for {} require an abi3 build for supported Houdini Python versions: {}".format(
                platform,
                ", ".join(core_wheels),
            )
        )
    python_floor = QUICKINSTALL_PYTHON_FLOORS[platform]
    if not any(_wheel_supports_python(name, python_floor) for name in core_wheels):
        raise RuntimeError(
            "Core wheels for {} do not support the declared Python {}.{} floor: {}".format(
                platform,
                python_floor[0],
                python_floor[1],
                ", ".join(core_wheels),
            )
        )

    return {
        "platform": platform,
        "adapter": adapter_version,
        "core": expected_core_version,
        "server": adapter_version,
        "cli": adapter_version,
        "core_wheels": sorted(core_wheels),
        "python_min": "{}.{}".format(python_floor[0], python_floor[1]),
    }


def print_version_matrix(matrix: Dict[str, object]) -> None:
    print("Quickinstall version matrix:")
    print("  platform: {}".format(matrix["platform"]))
    print("  adapter: dcc-mcp-houdini {}".format(matrix["adapter"]))
    print("  core: dcc-mcp-core {}".format(matrix["core"]))
    print("  server: dcc-mcp-houdini {}".format(matrix["server"]))
    print("  CLI: dcc-mcp-houdini {}".format(matrix["cli"]))
    print("  bundled Core Python floor: {}".format(matrix["python_min"]))
    print("  core wheels:")
    for wheel in matrix["core_wheels"]:
        print("    - {}".format(wheel))


def assemble(platform: str, dist_dir: Path, output_dir: Path, core_version: Optional[str] = None) -> Path:
    if platform not in PLATFORMS:
        raise ValueError("Unsupported platform {!r}; expected {}".format(platform, ", ".join(PLATFORMS)))
    assert_versions_aligned()
    version = get_package_version()
    adapter_wheel = find_adapter_wheel(dist_dir, version)
    explicit_core_version = core_version is not None
    core_version = select_core_version(core_version)

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / "dcc_mcp_houdini_quickinstall_{}_v{}.zip".format(platform, version)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        root = tmp_dir / "dcc_mcp_houdini"
        wheels_dir = root / "wheels"
        packages_dir = root / "packages"
        scripts_dir = root / "scripts"
        toolbar_dir = root / "toolbar"
        wheels_dir.mkdir(parents=True)
        packages_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)
        toolbar_dir.mkdir(parents=True)

        shutil.copy2(str(adapter_wheel), str(wheels_dir / adapter_wheel.name))
        for core_wheel in download_core_wheels(core_version, platform, tmp_dir / "wheel-cache"):
            shutil.copy2(str(core_wheel), str(wheels_dir / core_wheel.name))

        (packages_dir / "dcc_mcp_houdini.json.template").write_text(_package_json_template(), encoding="utf-8")
        (scripts_dir / "dcc_mcp_houdini_bootstrap.py").write_text(
            _bootstrap_py(version),
            encoding="utf-8",
        )
        startup = _startup_py()
        for hook in ("123.py", "456.py"):
            (scripts_dir / hook).write_text(startup, encoding="utf-8")
        (toolbar_dir / "DCC-MCP.shelf").write_text(_shelf_file(), encoding="utf-8")
        (root / "install.ps1").write_text(_install_ps1(), encoding="utf-8")
        install_sh = root / "install.sh"
        install_sh.write_text(_install_sh(), encoding="utf-8")
        install_sh.chmod(0o755)
        (root / "README.txt").write_text(
            _readme(version, core_version, platform, explicit_core_version),
            encoding="utf-8",
        )

        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(str(zip_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*")):
                zf.write(str(path), str(path.relative_to(tmp_dir)).replace("\\", "/"))

    return zip_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--dist-dir", type=Path, default=PACKAGE_ROOT / "dist")
    parser.add_argument("--output-dir", type=Path, default=PACKAGE_ROOT / "dist_houdini")
    parser.add_argument(
        "--verify-zip", type=Path, help="Verify an existing quickinstall ZIP and print its version matrix."
    )
    parser.add_argument(
        "--expected-core-version", help="Expected bundled dcc-mcp-core version; defaults to latest compatible."
    )
    parser.add_argument(
        "--core-version", help="Bundle this validated dcc-mcp-core version instead of resolving latest."
    )
    args = parser.parse_args(argv)

    if args.verify_zip is not None:
        matrix = verify_quickinstall_zip(
            args.verify_zip, args.platform, args.expected_core_version or args.core_version
        )
        print_version_matrix(matrix)
        return 0

    zip_path = assemble(args.platform, args.dist_dir, args.output_dir, args.core_version)
    print("Created {}".format(zip_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
