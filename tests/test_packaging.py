"""Tests for Houdini quick-install package assembly."""

from __future__ import annotations

import importlib.util
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
    assert "dcc_mcp_houdini/wheels/{}".format(adapter_wheel.name) in names
    for core_wheel in core_wheels:
        assert "dcc_mcp_houdini/wheels/{}".format(core_wheel.name) in names
    assert "dcc_mcp_houdini/scripts/123.py" in names
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
    assert "get_server" in shelf_xml
    assert "setStatusMessage" in shelf_xml
    assert "displayMessage" not in shelf_xml


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
