"""Tests for Houdini quick-install package assembly."""

from __future__ import annotations

import importlib.util
import json
import os
import platform as runtime_platform
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


def _write_windows_installer_fixture(pkg, tmp_path: Path) -> Path:
    package_root = tmp_path / "quickinstall"
    templates_dir = package_root / "packages"
    templates_dir.mkdir(parents=True)
    (package_root / "install.ps1").write_text(pkg._install_ps1(), encoding="utf-8")
    (templates_dir / "dcc_mcp_houdini.json.template").write_text(pkg._package_json_template(), encoding="utf-8")
    return package_root


def _windows_powershell() -> Path:
    return Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def _runtime_core_wheel_name() -> str:
    machine = runtime_platform.machine().lower()
    if sys.platform == "win32":
        return "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl"
    if sys.platform == "darwin":
        return "dcc_mcp_core-0.20.14-cp38-abi3-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2.whl"
    architecture = "aarch64" if machine in {"aarch64", "arm64"} else "x86_64"
    return "dcc_mcp_core-0.20.14-cp38-abi3-manylinux_2_17_{}.manylinux2014_{}.whl".format(
        architecture,
        architecture,
    )


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
        install_ps1 = zf.read("dcc_mcp_houdini/install.ps1").decode("utf-8")
        install_sh = zf.read("dcc_mcp_houdini/install.sh").decode("utf-8")
        readme = zf.read("dcc_mcp_houdini/README.txt").decode("utf-8")
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
        "dcc_mcp_houdini_copy_id",
        "dcc_mcp_houdini_server_info",
        "dcc_mcp_houdini_about",
        "dcc_mcp_houdini_start",
        "dcc_mcp_houdini_stop",
    }
    assert "wait_ready=False" in shelf_xml
    assert "Copy Instance ID" in shelf_xml
    assert "Server Info" in shelf_xml
    assert "About DCC MCP" in shelf_xml
    assert "PySide2" in shelf_xml
    assert "clipboard" in shelf_xml
    assert 'os.environ.get("DCC_MCP_REGISTRY_DIR")' in bootstrap
    assert "registry_dir=registry_dir" in bootstrap
    assert 'os.environ.get("DCC_MCP_BACKGROUND_RENDER") == "1"' in bootstrap
    assert "_require_compatible_core_wheel(wheels)" in bootstrap
    assert "not hou.isUIAvailable()" in bootstrap
    assert "hython -m dcc_mcp_houdini" in bootstrap
    assert '[string]$PackagesDir = ""' in install_ps1
    assert "$env:DCC_MCP_HOUDINI_PACKAGES_DIR" in install_ps1
    assert '"$(uname -s)" = "Darwin"' in install_sh
    assert "$HOME/Library/Preferences/houdini/$HOUDINI_VERSION/packages" in install_sh
    assert "$HOME/houdini$HOUDINI_VERSION/packages" in install_sh
    assert "Bundled Core Python compatibility: 3.7 or newer on win64." in readme
    assert "get_server" in shelf_xml
    assert "setStatusMessage" in shelf_xml
    assert "displayMessage" in shelf_xml


@pytest.mark.packaging
def test_quickinstall_package_leaves_autostart_to_user_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()

    version = pkg.get_package_version()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    adapter_wheel = dist_dir / "dcc_mcp_houdini-{}-py3-none-any.whl".format(version)
    adapter_wheel.write_bytes(b"adapter")
    core_wheel = tmp_path / "dcc_mcp_core-0.18.2-cp38-abi3-win_amd64.whl"
    core_wheel.write_bytes(b"core")

    monkeypatch.setattr(pkg, "resolve_core_version", lambda min_version=pkg.MIN_CORE_VERSION: "0.18.2")
    monkeypatch.setattr(pkg, "download_core_wheels", lambda version, platform, dest_dir: [core_wheel])

    zip_path = pkg.assemble("win64", dist_dir, tmp_path / "out")

    with zipfile.ZipFile(zip_path) as zf:
        package_json = json.loads(zf.read("dcc_mcp_houdini/packages/dcc_mcp_houdini.json.template").decode("utf-8"))
    environment_names = {next(iter(entry)) for entry in package_json["env"]}
    assert "DCC_MCP_HOUDINI_AUTOSTART" not in environment_names


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
    core_wheel = tmp_path / "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl"
    core_wheel.write_bytes(b"core")

    def fail_resolve(min_version=pkg.MIN_CORE_VERSION):
        raise AssertionError("explicit core version should skip PyPI latest resolution")

    def download_core_wheels(version_arg, platform, dest_dir):
        assert version_arg == "0.20.14"
        assert platform == "win64"
        return [core_wheel]

    monkeypatch.setattr(pkg, "resolve_core_version", fail_resolve)
    monkeypatch.setattr(pkg, "download_core_wheels", download_core_wheels)

    zip_path = pkg.assemble("win64", dist_dir, tmp_path / "out", core_version="0.20.14")

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        readme = zf.read("dcc_mcp_houdini/README.txt").decode("utf-8")
    assert "dcc_mcp_houdini/wheels/{}".format(core_wheel.name) in names
    assert "dcc-mcp-core wheels: 0.20.14" in readme
    assert "Core bundle policy: explicit validated dcc-mcp-core 0.20.14." in readme


def test_verify_quickinstall_zip_rejects_bundled_core_drift(tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64_v0.10.1.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.19.33-cp38-abi3-win_amd64.whl",
    )

    with pytest.raises(RuntimeError, match="Bundled core drift"):
        pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.20.14")


def test_verify_quickinstall_zip_rejects_python_specific_core_only(tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64_v0.10.1.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl",
    )

    with pytest.raises(RuntimeError, match="require an abi3 build"):
        pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.20.14")


def test_verify_quickinstall_zip_rejects_unknown_core_abi_even_with_valid_wheel(
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()
    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64_v0.10.1.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl",
        "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl",
        "dcc_mcp_core-0.20.14-cp38-cp38evil-win_amd64.whl",
    )

    with pytest.raises(RuntimeError, match="unsupported interpreter/ABI"):
        pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.20.14")


@pytest.mark.parametrize(
    "additional_wheel",
    [
        "unexpected_dependency-1.0.0-py3-none-any.whl",
        "dcc_mcp_houdini-{version}-1-py3-none-any.whl",
    ],
)
def test_verify_quickinstall_zip_rejects_ambiguous_vendor_wheel_set(
    tmp_path: Path,
    additional_wheel: str,
) -> None:
    pkg = _load_packaging_script()
    version = pkg.get_package_version()
    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64_v0.10.1.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(version),
        "dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl",
        "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl",
        additional_wheel.format(version=version),
    )

    with pytest.raises(RuntimeError, match="vendor wheel set"):
        pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.20.14")


def test_verify_quickinstall_zip_requires_scene_load_hook(tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl",
        include_scene_hook=False,
    )

    with pytest.raises(RuntimeError, match="/scripts/456.py"):
        pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.20.14")


def test_verify_quickinstall_zip_prints_version_matrix(tmp_path: Path) -> None:
    pkg = _load_packaging_script()

    zip_path = tmp_path / "dcc_mcp_houdini_quickinstall_win64_v0.10.1.zip"
    _write_quickinstall_zip(
        zip_path,
        "dcc_mcp_houdini-{}-py3-none-any.whl".format(pkg.get_package_version()),
        "dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl",
        "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl",
    )

    matrix = pkg.verify_quickinstall_zip(zip_path, "win64", expected_core_version="0.20.14")

    assert matrix["adapter"] == pkg.get_package_version()
    assert matrix["core"] == "0.20.14"
    assert matrix["server"] == pkg.get_package_version()
    assert matrix["cli"] == pkg.get_package_version()
    assert matrix["python_min"] == "3.7"


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell 5.1")
def test_windows_installer_writes_bomless_package_json(tmp_path: Path) -> None:
    pkg = _load_packaging_script()
    package_root = _write_windows_installer_fixture(pkg, tmp_path)

    powershell = _windows_powershell()
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
        timeout=30,
    )

    target = home / "Documents/houdini21.0/packages/dcc_mcp_houdini.json"
    raw = target.read_bytes()
    assert raw[:1] == b"{"
    expected = pkg._package_json_template().replace("__PACKAGE_ROOT__", package_root.as_posix())
    assert json.loads(raw) == json.loads(expected)


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell 5.1")
def test_windows_installer_explicit_packages_dir_isolated_from_home(tmp_path: Path) -> None:
    pkg = _load_packaging_script()
    package_root = _write_windows_installer_fixture(pkg, tmp_path)

    powershell = _windows_powershell()
    automatic_home = tmp_path / "automatic-home"
    environment_home = tmp_path / "environment-home"
    environment_override = tmp_path / "environment-override"
    explicit_override = tmp_path / "explicit-override"
    automatic_home.mkdir()
    environment_home.mkdir()
    env = os.environ.copy()
    env["USERPROFILE"] = str(automatic_home)
    env["HOME"] = str(environment_home)
    env["DCC_MCP_HOUDINI_PACKAGES_DIR"] = str(environment_override)

    probe = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", "[Console]::Out.Write($HOME)"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert Path(probe.stdout) == automatic_home
    assert Path(probe.stdout) != environment_home

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
            "-PackagesDir",
            str(explicit_override),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert (explicit_override / "dcc_mcp_houdini.json").is_file()
    assert not (environment_override / "dcc_mcp_houdini.json").exists()
    assert not (automatic_home / "Documents/houdini21.0/packages/dcc_mcp_houdini.json").exists()
    assert not (environment_home / "Documents/houdini21.0/packages/dcc_mcp_houdini.json").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell 5.1")
def test_windows_installer_uses_packages_dir_environment_override(tmp_path: Path) -> None:
    pkg = _load_packaging_script()
    package_root = _write_windows_installer_fixture(pkg, tmp_path)

    powershell = _windows_powershell()
    automatic_home = tmp_path / "automatic-home"
    environment_override = tmp_path / "environment-override"
    automatic_home.mkdir()
    env = os.environ.copy()
    env["USERPROFILE"] = str(automatic_home)
    env["DCC_MCP_HOUDINI_PACKAGES_DIR"] = str(environment_override)

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
        timeout=30,
    )

    assert (environment_override / "dcc_mcp_houdini.json").is_file()
    assert not (automatic_home / "Documents/houdini21.0/packages/dcc_mcp_houdini.json").exists()


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
    with zipfile.ZipFile(wheels / _runtime_core_wheel_name(), "w"):
        pass
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


def test_bootstrap_persists_early_vendor_failure_before_core_is_available(tmp_path: Path) -> None:
    pkg = _load_packaging_script()
    root = tmp_path / "dcc_mcp_houdini"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    bootstrap = scripts / "dcc_mcp_houdini_bootstrap.py"
    bootstrap.write_text(pkg._bootstrap_py(), encoding="utf-8")

    code = r"""
import importlib.util
import os
from pathlib import Path
import sys

root = Path(sys.argv[1])
os.environ["DCC_MCP_HOUDINI_ROOT"] = str(root)
spec = importlib.util.spec_from_file_location("dcc_mcp_houdini_bootstrap", root / "scripts/dcc_mcp_houdini_bootstrap.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.bootstrap_and_start()
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code, str(root)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "No bundled wheels" in completed.stderr
    error_log = root / ".dcc-mcp" / "logs" / "houdini-bootstrap-early.host-errors.log"
    payload = json.loads(error_log.read_text(encoding="utf-8"))
    assert payload["phase"] == "vendor-bootstrap"
    assert payload["error_type"] == "RuntimeError"
    assert "No bundled wheels" in payload["message"]


@pytest.mark.parametrize("replace_succeeds", [True, False])
def test_bootstrap_vendor_upgrade_is_staged_and_preserves_previous_state_on_failure(
    tmp_path: Path,
    replace_succeeds: bool,
) -> None:
    pkg = _load_packaging_script()
    root = tmp_path / "dcc_mcp_houdini"
    wheels = root / "wheels"
    vendor = root / "vendor"
    scripts = root / "scripts"
    wheels.mkdir(parents=True)
    (vendor / "dcc_mcp_core").mkdir(parents=True)
    scripts.mkdir()
    (vendor / "old.txt").write_text("previous", encoding="utf-8")
    (vendor / ".dcc_mcp_houdini_wheels").write_text("old", encoding="utf-8")
    (vendor / "dcc_mcp_core" / "__init__.py").write_text("", encoding="utf-8")
    (vendor / "dcc_mcp_core" / "install_lifecycle.py").write_text(
        """from pathlib import Path
import shutil

def inspect_install_root(path):
    return {{"success": True, "requires_restart": False, "install_root": str(path)}}

def safe_replace_tree(source, destination):
    if {replace!r}:
        shutil.copytree(str(source), str(destination))
        return {{"success": True, "requires_restart": False}}
    return {{"success": False, "requires_restart": False, "message": "injected replace failure"}}

def safe_remove_tree(path):
    shutil.rmtree(str(path), ignore_errors=True)
    return {{"success": True, "requires_restart": False}}
""".format(replace=replace_succeeds),
        encoding="utf-8",
    )
    with zipfile.ZipFile(wheels / "dcc_mcp_houdini-2.0.0-py3-none-any.whl", "w") as zf:
        zf.writestr("dcc_mcp_houdini/new.txt", "replacement")
    with zipfile.ZipFile(wheels / _runtime_core_wheel_name(), "w"):
        pass
    bootstrap = scripts / "dcc_mcp_houdini_bootstrap.py"
    bootstrap.write_text(pkg._bootstrap_py(), encoding="utf-8")

    code = r"""
import importlib.util
from pathlib import Path
import sys

root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("dcc_mcp_houdini_bootstrap", root / "scripts/dcc_mcp_houdini_bootstrap.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ensure_vendor(root)
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code, str(root)],
        check=False,
        capture_output=True,
        text=True,
    )

    if replace_succeeds:
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert not (vendor / "old.txt").exists()
        assert (vendor / "dcc_mcp_houdini" / "new.txt").read_text(encoding="utf-8") == "replacement"
    else:
        assert completed.returncode != 0
        assert "injected replace failure" in completed.stderr
        assert (vendor / "old.txt").read_text(encoding="utf-8") == "previous"
        assert not (vendor / "dcc_mcp_houdini" / "new.txt").exists()
    assert not list(root.glob(".vendor-stage-*"))
    assert not list(root.glob(".vendor-backup-*"))


def test_pick_core_wheels_selects_only_runtime_compatible_native_tags() -> None:
    pkg = _load_packaging_script()

    files = [
        {"filename": "dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl"},
        {"filename": "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl"},
        {"filename": "dcc_mcp_core-0.20.14-py3-none-any.whl"},
    ]

    py37 = pkg.pick_core_wheel_files(files, "win64", python_version=(3, 7))
    py312 = pkg.pick_core_wheel_files(files, "win64", python_version=(3, 12))

    assert [item["filename"] for item in py37] == ["dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl"]
    assert [item["filename"] for item in py312] == ["dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl"]


def test_core_02014_wheel_matrix_rejects_macos_python37_and_accepts_declared_floors() -> None:
    pkg = _load_packaging_script()
    files = [
        {"filename": "dcc_mcp_core-0.20.14-cp37-cp37m-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"},
        {"filename": "dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl"},
        {
            "filename": (
                "dcc_mcp_core-0.20.14-cp38-abi3-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2.whl"
            )
        },
        {"filename": "dcc_mcp_core-0.20.14-cp38-abi3-manylinux_2_17_x86_64.whl"},
        {"filename": "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl"},
        {"filename": "dcc_mcp_core-0.20.14-py3-none-any.whl"},
    ]

    assert pkg.pick_core_wheel_files(files, "macos", python_version=(3, 7)) == []
    assert [item["filename"] for item in pkg.pick_core_wheel_files(files, "macos", python_version=(3, 8))] == [
        files[2]["filename"]
    ]
    assert pkg.pick_core_wheel_files(files, "win64", python_version=(3, 7))
    assert pkg.pick_core_wheel_files(files, "linux", python_version=(3, 7))


def test_generated_bootstrap_fails_closed_before_extracting_unsupported_core_tag(tmp_path: Path) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mac_wheel = tmp_path / (
        "dcc_mcp_core-0.20.14-cp38-abi3-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2.whl"
    )

    with pytest.raises(RuntimeError, match=r"macOS.*Python 3\.8 or newer"):
        module._require_compatible_core_wheel(
            [mac_wheel],
            python_version=(3, 7),
            platform_name="darwin",
            machine="x86_64",
        )
    assert module._require_compatible_core_wheel(
        [mac_wheel],
        python_version=(3, 8),
        platform_name="darwin",
        machine="arm64",
    ) == [mac_wheel]


@pytest.mark.parametrize("machine", ["ppc64", "riscv64"])
def test_generated_bootstrap_rejects_universal2_on_unsupported_macos_machine_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    machine: str,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "quickinstall"
    wheels = root / "wheels"
    wheels.mkdir(parents=True)
    wheel = wheels / "dcc_mcp_core-0.20.14-cp38-abi3-macosx_10_12_universal2.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("must-not-extract.txt", "unsupported")
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(module.platform, "machine", lambda: machine)

    with pytest.raises(RuntimeError, match=r"no wheel matches Python"):
        module.ensure_vendor(root)

    assert not (root / "vendor").exists()
    assert not list(root.glob(".vendor-stage-*"))


def test_generated_bootstrap_extracts_only_runtime_selected_core_wheel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "quickinstall"
    wheels = root / "wheels"
    wheels.mkdir(parents=True)
    adapter = wheels / "dcc_mcp_houdini-2.0.0-py3-none-any.whl"
    compatible = wheels / ("dcc_mcp_core-0.20.14-cp38-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl")
    incompatible = wheels / ("dcc_mcp_core-0.20.14-cp38-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl")
    with zipfile.ZipFile(adapter, "w") as archive:
        archive.writestr("dcc_mcp_houdini/adapter.txt", "adapter")
    with zipfile.ZipFile(compatible, "w") as archive:
        archive.writestr("dcc_mcp_core/selected-x86_64.txt", "selected")
    with zipfile.ZipFile(incompatible, "w") as archive:
        archive.writestr("dcc_mcp_core/must-not-extract-aarch64.txt", "incompatible")
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")

    vendor = module.ensure_vendor(root)

    assert (vendor / "dcc_mcp_houdini" / "adapter.txt").is_file()
    assert (vendor / "dcc_mcp_core" / "selected-x86_64.txt").is_file()
    assert not (vendor / "dcc_mcp_core" / "must-not-extract-aarch64.txt").exists()
    marker = (vendor / ".dcc_mcp_houdini_wheels").read_text(encoding="utf-8")
    assert compatible.name in marker
    assert incompatible.name not in marker


def test_generated_bootstrap_rejects_overlapping_wheel_members_before_extraction(
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "quickinstall"
    wheels = root / "wheels"
    wheels.mkdir(parents=True)
    adapter = wheels / "dcc_mcp_houdini-2.0.0-py3-none-any.whl"
    core = wheels / _runtime_core_wheel_name()
    with zipfile.ZipFile(adapter, "w") as archive:
        archive.writestr("shared/owned.txt", "adapter")
    with zipfile.ZipFile(core, "w") as archive:
        archive.writestr("shared/owned.txt", "core")

    with pytest.raises(RuntimeError, match="overlapping wheel member"):
        module.ensure_vendor(root)

    assert not (root / "vendor").exists()
    assert not list(root.glob(".vendor-stage-*"))


@pytest.mark.parametrize("member", ["../escape.txt", "/absolute.txt", "C:/drive.txt"])
def test_generated_bootstrap_rejects_unsafe_wheel_members_before_extraction(
    tmp_path: Path,
    member: str,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "quickinstall"
    wheels = root / "wheels"
    wheels.mkdir(parents=True)
    adapter = wheels / "dcc_mcp_houdini-2.0.0-py3-none-any.whl"
    core = wheels / _runtime_core_wheel_name()
    with zipfile.ZipFile(adapter, "w") as archive:
        archive.writestr(member, "must-not-extract")
    with zipfile.ZipFile(core, "w"):
        pass

    with pytest.raises(RuntimeError, match="unsafe wheel member"):
        module.ensure_vendor(root)

    assert not (root / "vendor").exists()
    assert not list(root.glob(".vendor-stage-*"))


def test_generated_bootstrap_rejects_unknown_core_abi_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "quickinstall"
    wheels = root / "wheels"
    wheels.mkdir(parents=True)
    adapter = wheels / "dcc_mcp_houdini-2.0.0-py3-none-any.whl"
    core = wheels / "dcc_mcp_core-0.20.14-cp38-cp38evil-win_amd64.whl"
    with zipfile.ZipFile(adapter, "w"):
        pass
    with zipfile.ZipFile(core, "w") as archive:
        archive.writestr("must-not-extract.txt", "unknown ABI")
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.platform, "machine", lambda: "AMD64")

    with pytest.raises(RuntimeError, match="unsupported interpreter/ABI"):
        module.ensure_vendor(root)

    assert not (root / "vendor").exists()
    assert not list(root.glob(".vendor-stage-*"))


def test_generated_bootstrap_rejects_malformed_additional_core_wheel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "quickinstall"
    wheels = root / "wheels"
    wheels.mkdir(parents=True)
    names = [
        "dcc_mcp_houdini-2.0.0-py3-none-any.whl",
        "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl",
        "dcc_mcp_core-0.20.14-cp38-abi3-notwin_amd64.whl",
    ]
    for name in names:
        with zipfile.ZipFile(wheels / name, "w"):
            pass
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.platform, "machine", lambda: "AMD64")

    with pytest.raises(RuntimeError, match="unsupported interpreter/ABI"):
        module.ensure_vendor(root)

    assert not (root / "vendor").exists()
    assert not list(root.glob(".vendor-stage-*"))


@pytest.mark.parametrize(
    "additional_wheel",
    [
        "unexpected_dependency-1.0.0-py3-none-any.whl",
        "dcc_mcp_houdini-2.0.1-py3-none-any.whl",
    ],
)
def test_generated_bootstrap_rejects_unselected_or_duplicate_adapter_wheels(
    tmp_path: Path,
    additional_wheel: str,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "quickinstall"
    wheels = root / "wheels"
    wheels.mkdir(parents=True)
    names = [
        "dcc_mcp_houdini-2.0.0-py3-none-any.whl",
        _runtime_core_wheel_name(),
        additional_wheel,
    ]
    for name in names:
        with zipfile.ZipFile(wheels / name, "w"):
            pass

    with pytest.raises(RuntimeError, match="vendor wheel set"):
        module.ensure_vendor(root)

    assert not (root / "vendor").exists()
    assert not list(root.glob(".vendor-stage-*"))


@pytest.mark.parametrize(
    ("python_tag", "abi_tag", "python_version", "expected"),
    [
        ("cp37", "cp37m", (3, 7), True),
        ("cp37", "abi3", (3, 7), False),
        ("cp38", "abi3", (3, 12), True),
        ("cp38", "cp38evil", (3, 8), False),
        ("cp38", "unknown", (3, 8), False),
    ],
)
def test_assembly_and_generated_bootstrap_require_exact_known_abi_tags(
    tmp_path: Path,
    python_tag: str,
    abi_tag: str,
    python_version: tuple[int, int],
    expected: bool,
) -> None:
    pkg = _load_packaging_script()
    filename = "dcc_mcp_core-0.20.14-{}-{}-win_amd64.whl".format(python_tag, abi_tag)
    assert pkg._wheel_supports_python(filename, python_version) is expected
    selected = pkg.pick_core_wheel_files(
        [{"filename": filename}],
        "win64",
        python_version=python_version,
    )
    assert bool(selected) is expected

    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheel = tmp_path / filename
    assert module._native_wheel_supports_runtime(wheel, python_version, "win32", "AMD64") is expected


@pytest.mark.parametrize(
    ("platform_name", "machine", "platform_tag", "expected"),
    [
        ("darwin", "x86_64", "macosx_10_12_universal2", True),
        ("darwin", "arm64", "macosx_11_0_universal2", True),
        ("darwin", "ppc64", "macosx_10_12_universal2", False),
        ("darwin", "riscv64", "macosx_10_12_universal2", False),
        ("darwin", "arm64", "notmacosx_11_0_universal2", False),
        ("darwin", "arm64", "macosx_broken_universal2", False),
        ("win32", "AMD64", "win_amd64", True),
        ("win32", "AMD64", "notwin_amd64", False),
        ("linux", "x86_64", "manylinux_2_17_x86_64", True),
        ("linux", "aarch64", "manylinux2014_aarch64", True),
        ("linux", "x86_64", "linux_x86_64", True),
        ("linux", "x86_64", "notmanylinux_2_17_x86_64", False),
        ("linux", "aarch64", "manylinux_broken_aarch64", False),
    ],
)
def test_generated_bootstrap_strictly_parses_platform_and_machine_tags(
    tmp_path: Path,
    platform_name: str,
    machine: str,
    platform_tag: str,
    expected: bool,
) -> None:
    pkg = _load_packaging_script()
    bootstrap_path = tmp_path / "dcc_mcp_houdini_bootstrap.py"
    bootstrap_path.write_text(pkg._bootstrap_py(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generated_houdini_bootstrap", bootstrap_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheel = tmp_path / "dcc_mcp_core-0.20.14-cp38-abi3-{}.whl".format(platform_tag)

    assert module._native_wheel_supports_runtime(wheel, (3, 8), platform_name, machine) is expected


@pytest.mark.parametrize(
    ("target", "filename"),
    [
        ("macos", "dcc_mcp_core-0.20.14-cp38-abi3-notmacosx_11_0_universal2.whl"),
        ("win64", "dcc_mcp_core-0.20.14-cp38-abi3-notwin_amd64.whl"),
        ("linux", "dcc_mcp_core-0.20.14-cp38-abi3-notmanylinux_2_17_x86_64.whl"),
    ],
)
def test_package_assembly_rejects_platform_substring_counterexamples(target: str, filename: str) -> None:
    pkg = _load_packaging_script()

    assert pkg.pick_core_wheel_files([{"filename": filename}], target, python_version=(3, 8)) == []


def test_resolve_core_version_skips_release_without_cross_platform_abi3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pkg = _load_packaging_script()
    releases = {
        "0.20.14": [
            {"filename": "dcc_mcp_core-0.20.14-cp37-cp37m-win_amd64.whl"},
            {"filename": "dcc_mcp_core-0.20.14-cp38-abi3-win_amd64.whl"},
            {"filename": "dcc_mcp_core-0.20.14-cp37-cp37m-manylinux_2_17_x86_64.whl"},
            {"filename": "dcc_mcp_core-0.20.14-cp38-abi3-manylinux_2_17_x86_64.whl"},
            {"filename": "dcc_mcp_core-0.20.14-cp38-abi3-macosx_11_0_universal2.whl"},
        ],
        "0.20.15": [
            {"filename": "dcc_mcp_core-0.20.15-cp37-cp37m-win_amd64.whl"},
            {"filename": "dcc_mcp_core-0.20.15-cp38-abi3-manylinux_2_17_x86_64.whl"},
            {"filename": "dcc_mcp_core-0.20.15-cp38-abi3-macosx_11_0_universal2.whl"},
        ],
    }
    monkeypatch.setattr(pkg, "_fetch_json", lambda _url: {"releases": releases})

    assert pkg.resolve_core_version() == "0.20.14"
