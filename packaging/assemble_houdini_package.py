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
from typing import Dict, List, Optional

from packaging.version import Version

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"
CORE_PACKAGE = "dcc-mcp-core"
MIN_CORE_VERSION = "0.19.69"
PLATFORMS = ("win64", "linux", "macos")
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
    compatible = [v for v in available if v >= Version(min_version) and v < Version("1.0.0")]
    if not compatible:
        raise RuntimeError("No compatible {} release found >= {}".format(CORE_PACKAGE, min_version))
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


def _wheel_matches_platform(filename: str, platform: str) -> bool:
    if not filename.endswith(".whl"):
        return False
    if platform == "win64":
        return "win_amd64" in filename
    if platform == "linux":
        return "linux" in filename and ("x86_64" in filename or "aarch64" in filename)
    if platform == "macos":
        return "macosx" in filename
    return False


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


def pick_core_wheel_files(release_files: List[Dict[str, object]], platform: str) -> List[Dict[str, object]]:
    candidates = [f for f in release_files if _wheel_matches_platform(str(f.get("filename", "")), platform)]
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


def _bootstrap_py() -> str:
    return r'''"""Bootstrap bundled dcc-mcp-houdini wheels inside Houdini."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import sys
import zipfile


def _package_root() -> Path:
    env_root = os.environ.get("DCC_MCP_HOUDINI_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _wheel_marker(wheels) -> str:
    return "\n".join(sorted("{}:{}".format(w.name, w.stat().st_size) for w in wheels))


def ensure_vendor(root: Path) -> Path:
    wheels_dir = root / "wheels"
    vendor_dir = root / "vendor"
    wheels = sorted(wheels_dir.glob("*.whl"))
    if not wheels:
        raise RuntimeError("No bundled wheels found under {}".format(wheels_dir))
    marker = vendor_dir / ".dcc_mcp_houdini_wheels"
    desired = _wheel_marker(wheels)
    if marker.is_file() and marker.read_text(encoding="utf-8") == desired:
        return vendor_dir
    if vendor_dir.exists():
        shutil.rmtree(str(vendor_dir))
    vendor_dir.mkdir(parents=True, exist_ok=True)
    for wheel in wheels:
        with zipfile.ZipFile(str(wheel), "r") as zf:
            zf.extractall(str(vendor_dir))
    marker.write_text(desired, encoding="utf-8")
    return vendor_dir


def bootstrap_and_start() -> object:
    if os.environ.get("DCC_MCP_BACKGROUND_RENDER") == "1":
        return None
    root = _package_root()
    vendor = ensure_vendor(root)
    vendor_str = str(vendor)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)
    importlib.invalidate_caches()

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
    server = _load_bootstrap().bootstrap_and_start()
    if server is not None:
        print("dcc-mcp-houdini MCP server started: {}".format(server.mcp_url))
except Exception as exc:
    print("dcc-mcp-houdini autostart failed: {}".format(exc))
'''


def _shelf_file() -> str:
    return r"""<?xml version="1.0" encoding="UTF-8"?>
<shelfDocument>
  <toolshelf name="DCC-MCP" label="DCC-MCP">
    <memberTool name="dcc_mcp_houdini_start"/>
    <memberTool name="dcc_mcp_houdini_stop"/>
    <memberTool name="dcc_mcp_houdini_status"/>
    <memberTool name="dcc_mcp_houdini_docs"/>
  </toolshelf>
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
  <tool name="dcc_mcp_houdini_status" label="Status" icon="BUTTONS_info" helpText="Show the DCC-MCP Houdini server status.">
    <script scriptType="python"><![CDATA[
try:
    import dcc_mcp_houdini

    server = dcc_mcp_houdini.get_server()
    if server is not None and getattr(server, "is_running", False):
        message = "DCC-MCP Houdini server is running: {}".format(server.mcp_url)
    else:
        message = "DCC-MCP Houdini server is not running."
except Exception as exc:
    message = "DCC-MCP Houdini status failed: {}".format(exc)

try:
    import hou

    hou.ui.setStatusMessage(message)
except Exception:
    print(message)
]]></script>
  </tool>
  <tool name="dcc_mcp_houdini_docs" label="Docs" icon="BUTTONS_help" helpText="Open DCC-MCP Houdini documentation.">
    <script scriptType="python"><![CDATA[
import webbrowser

url = "https://github.com/dcc-mcp/dcc-mcp-houdini"
webbrowser.open(url)

try:
    import hou

    hou.ui.setStatusMessage("Opened DCC-MCP Houdini docs: {}".format(url))
except Exception:
    print("Opened DCC-MCP Houdini docs: {}".format(url))
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
PACKAGES_DIR="${DCC_MCP_HOUDINI_PACKAGES_DIR:-$HOME/houdini$HOUDINI_VERSION/packages}"

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
        core_policy = "latest non-prerelease dcc-mcp-core >= {},<1.0.0 at assembly time.".format(MIN_CORE_VERSION)
    return """dcc-mcp-houdini quick install package
======================================

Version: {version}
dcc-mcp-core wheels: {core_version}
Platform: {platform}
Core bundle policy: {core_policy}
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
""".format(version=version, core_version=core_version, platform=platform, core_policy=core_policy)


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

    return {
        "platform": platform,
        "adapter": adapter_version,
        "core": expected_core_version,
        "server": adapter_version,
        "cli": adapter_version,
        "core_wheels": sorted(core_wheels),
    }


def print_version_matrix(matrix: Dict[str, object]) -> None:
    print("Quickinstall version matrix:")
    print("  platform: {}".format(matrix["platform"]))
    print("  adapter: dcc-mcp-houdini {}".format(matrix["adapter"]))
    print("  core: dcc-mcp-core {}".format(matrix["core"]))
    print("  server: dcc-mcp-houdini {}".format(matrix["server"]))
    print("  CLI: dcc-mcp-houdini {}".format(matrix["cli"]))
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
        (scripts_dir / "dcc_mcp_houdini_bootstrap.py").write_text(_bootstrap_py(), encoding="utf-8")
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
