"""Tests for Houdini quick-install package assembly."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest


def _load_packaging_script():
    path = Path(__file__).resolve().parents[1] / "packaging" / "assemble_houdini_package.py"
    spec = importlib.util.spec_from_file_location("assemble_houdini_package", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_quickinstall_zip(zip_path: Path, *wheel_names: str, include_scene_hook: bool = True) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("dcc_mcp_houdini/scripts/123.py", "")
        if include_scene_hook:
            zf.writestr("dcc_mcp_houdini/scripts/456.py", "")
        zf.writestr("dcc_mcp_houdini/scripts/dcc_mcp_houdini_bootstrap.py", "")
        zf.writestr("dcc_mcp_houdini/packages/dcc_mcp_houdini.json.template", "")
        zf.writestr("dcc_mcp_houdini/README.txt", "")
        for wheel_name in wheel_names:
            zf.writestr("dcc_mcp_houdini/wheels/{}".format(wheel_name), "")


@pytest.mark.packaging
def test_assemble_houdini_package_without_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    version = pkg.get_package_version()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    adapter_wheel = dist_dir / "dcc_mcp_houdini-{}-py3-none-any.whl".format(version)
    adapter_wheel.write_bytes(b"adapter")
    core_wheels = [
        tmp_path / "dcc_mcp_core-0.18.2-cp37-cp37m-win_amd64.whl",
        tmp_path / "dcc_mcp_core-0.18.2-cp38-abi3-win_amd64.whl",
    ]
    for core_wheel in core_wheels:
        core_wheel.write_bytes(b"core")

    monkeypatch.setattr(pkg, "resolve_core_version", lambda min_version=pkg.MIN_CORE_VERSION: "0.18.2")
    monkeypatch.setattr(pkg, "download_core_wheels", lambda version, platform, dest_dir: core_wheels)

    zip_path = pkg.assemble("win64", dist_dir, tmp_path / "out")

    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        shelf_xml = zf.read("dcc_mcp_houdini/toolbar/DCC-MCP.shelf").decode("utf-8")
        bootstrap = zf.read("dcc_mcp_houdini/scripts/dcc_mcp_houdini_bootstrap.py").decode("utf-8")
        startup = zf.read("dcc_mcp_houdini/scripts/123.py")
        scene_load = zf.read("dcc_mcp_houdini/scripts/456.py")
    assert "dcc_mcp_houdini/wheels/{}".format(adapter_wheel.name) in names
    for core_wheel in core_wheels:
        assert "dcc_mcp_houdini/wheels/{}".format(core_wheel.name) in names
    assert "dcc_mcp_houdini/scripts/123.py" in names
    assert "dcc_mcp_houdini/scripts/456.py" in names
    assert startup == scene_load
    assert "dcc_mcp_houdini/scripts/dcc_mcp_houdini_bootstrap.py" in names
    assert "dcc_mcp_houdini/toolbar/DCC-MCP.shelf" in names
    assert "dcc_mcp_houdini/packages/dcc_mcp_houdini.json.template" in names
    assert "dcc_mcp_houdini/install.ps1" in names
    assert "dcc_mcp_houdini/install.sh" in names

    shelf = ET.fromstring(shelf_xml)
    tool_names = {tool.attrib["name"] for tool in shelf.findall("tool")}
    assert tool_names == {
        "dcc_mcp_houdini_start",
        "dcc_mcp_houdini_stop",
        "dcc_mcp_houdini_status",
        "dcc_mcp_houdini_docs",
    }
    assert "wait_ready=False" in shelf_xml
    assert 'os.environ.get("DCC_MCP_REGISTRY_DIR")' in bootstrap
    assert "registry_dir=registry_dir" in bootstrap
    assert 'os.environ.get("DCC_MCP_BACKGROUND_RENDER") == "1"' in bootstrap
    assert "get_server" in shelf_xml
    assert "setStatusMessage" in shelf_xml
    assert "displayMessage" not in shelf_xml


@pytest.mark.packaging
def test_assemble_houdini_package_can_pin_validated_core(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()

    version = pkg.get_package_version()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    adapter_wheel = dist_dir / "dcc_mcp_houdini-{}-py3-none-any.whl".format(version)
    adapter_wheel.write_bytes(b"adapter")
    core_wheel = tmp_path / "dcc_mcp_core-0.19.45-cp38-abi3-win_amd64.whl"
    core_wheel.write_bytes(b"core")

    def fail_resolve(min_version=pkg.MIN_CORE_VERSION):
        raise AssertionError("explicit core version should skip PyPI latest resolution")

    def download_core_wheels(version_arg, platform, dest_dir):
        assert version_arg == "0.19.45"
        assert platform == "win64"
        return [core_wheel]

    monkeypatch.setattr(pkg, "resolve_core_version", fail_resolve)
    monkeypatch.setattr(pkg, "download_core_wheels", download_core_wheels)

    zip_path = pkg.assemble("win64", dist_dir, tmp_path / "out", core_version="0.19.45")

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        readme = zf.read("dcc_mcp_houdini/README.txt").decode("utf-8")
    assert "dcc_mcp_houdini/wheels/{}".format(core_wheel.name) in names
    assert "dcc-mcp-core wheels: 0.19.45" in readme
    assert "Core bundle policy: explicit validated dcc-mcp-core 0.19.45." in readme


def test_verify_quickinstall_zip_rejects_bundled_core_drift(tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64_v0.10.1.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.19.33-cp38-abi3-win_amd64.whl",
    )

    with pytest.raises(RuntimeError, match="Bundled core drift"):
        pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.19.45")


def test_verify_quickinstall_zip_requires_scene_load_hook(tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.19.45-cp38-abi3-win_amd64.whl",
        include_scene_hook=False,
    )

    with pytest.raises(RuntimeError, match="/scripts/456.py"):
        pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.19.45")


def test_verify_quickinstall_zip_prints_version_matrix(tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64_v0.10.1.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.19.45-cp38-abi3-win_amd64.whl",
    )

    matrix = pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.19.45")

    assert matrix["adapter"] == pkg.get_package_version()
    assert matrix["core"] == "0.19.45"
    assert matrix["server"] == pkg.get_package_version()
    assert matrix["cli"] == pkg.get_package_version()


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell 5.1")
def test_windows_installer_writes_bomless_package_json(tmp_path: Path) -> None:
    pkg = _load_packaging_script()
    package_root = tmp_path / "quickinstall"
    packages_dir = package_root / "packages"
    packages_dir.mkdir(parents=True)
    (package_root / "install.ps1").write_text(pkg._install_ps1(), encoding="utf-8")
    (packages_dir / "dcc_mcp_houdini.json.template").write_text(pkg._package_json_template(), encoding="utf-8")

    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    home = tmp_path / "home"
    env = os.environ.copy()
    env["USERPROFILE"] = str(home)
    subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(package_root / "install.ps1"),
            "-HoudiniVersion",
            "21.0",
            "-PackageRoot",
            str(package_root),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    target = home / "Documents/houdini21.0/packages/dcc_mcp_houdini.json"
    raw = target.read_bytes()
    assert raw[:1] == b"{"
    expected = pkg._package_json_template().replace("__PACKAGE_ROOT__", package_root.as_posix())
    assert json.loads(raw) == json.loads(expected)


def test_startup_hook_uses_package_root_without_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    marker = tmp_path / "bootstrap_calls"
    (scripts / "dcc_mcp_houdini_bootstrap.py").write_text(
        """from pathlib import Path

class Server:
    mcp_url = "http://127.0.0.1:8765/mcp"

def bootstrap_and_start():
    marker = Path({marker!r})
    marker.write_text((marker.read_text() if marker.exists() else "") + "1")
    return Server()
""".format(marker=str(marker)),
        encoding="utf-8",
    )
    monkeypatch.setenv("DCC_MCP_HOUDINI_ROOT", str(tmp_path))

    exec(compile(pkg._startup_py(), "<houdini-startup>", "exec"), {})

    assert marker.read_text(encoding="utf-8") == "1"


def test_bootstrap_refreshes_cached_missing_vendor_path(tmp_path: Path) -> None:
    pkg = _load_packaging_script()
    root = tmp_path / "dcc_mcp_houdini"
    wheels = root / "wheels"
    scripts = root / "scripts"
    wheels.mkdir(parents=True)
    scripts.mkdir()
    with zipfile.ZipFile(wheels / "dcc_mcp_houdini-1.0.0-py3-none-any.whl", "w") as zf:
        zf.writestr(
            "dcc_mcp_houdini/__init__.py",
            "def start_server(**kwargs):\n    return kwargs\n",
        )
    bootstrap = scripts / "dcc_mcp_houdini_bootstrap.py"
    bootstrap.write_text(pkg._bootstrap_py(), encoding="utf-8")

    code = r"""
import importlib.util
import os
from pathlib import Path
import sys

root = Path(sys.argv[1])
vendor = str(root / "vendor")
sys.path.insert(0, vendor)
try:
    import dcc_mcp_houdini
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("vendor unexpectedly importable before extraction")
assert sys.path_importer_cache.get(vendor) is None

os.environ["DCC_MCP_HOUDINI_ROOT"] = str(root)
spec = importlib.util.spec_from_file_location(
    "dcc_mcp_houdini_bootstrap",
    root / "scripts" / "dcc_mcp_houdini_bootstrap.py",
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
server = module.bootstrap_and_start()
assert "port" not in server
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code, str(root)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_pick_core_wheels_includes_py37_and_abi3_for_platform() -> None:
    pkg = _load_packaging_script()

    files = [
        {"filename": "dcc_mcp_core-0.18.2-cp311-cp311-win_amd64.whl"},
        {"filename": "dcc_mcp_core-0.18.2-cp38-abi3-win_amd64.whl"},
        {"filename": "dcc_mcp_core-0.18.2-cp37-cp37m-win_amd64.whl"},
        {"filename": "dcc_mcp_core-0.18.2-cp38-abi3-manylinux_x86_64.whl"},
    ]
    picked = pkg.pick_core_wheel_files(files, "win64")
    assert [item["filename"] for item in picked] == [
        "dcc_mcp_core-0.18.2-cp38-abi3-win_amd64.whl",
        "dcc_mcp_core-0.18.2-cp311-cp311-win_amd64.whl",
        "dcc_mcp_core-0.18.2-cp37-cp37m-win_amd64.whl",
    ]
