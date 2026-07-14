"""Unit coverage for native Husk command and result contracts."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills" / "houdini-husk" / "scripts"


def _load_script(filename: str):
    path = SCRIPTS / filename
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"husk_test_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_husk_command_resolves_karma_alias() -> None:
    common = _load_script("_husk_common.py")

    command = common.build_husk_command("scene.usda", "beauty.exr", renderer="karma")

    assert command[:3] == ["husk", "--renderer", "BRAY_HdKarma"]


def test_husk_environment_restores_houdini_default_paths() -> None:
    common = _load_script("_husk_common.py")
    base = {"HOUDINI_PATH": "custom", "HOUDINI_SCRIPT_PATH": ""}

    environment = common.husk_subprocess_environment(base)

    assert environment["HOUDINI_PATH"].split(os.pathsep)[-1] == "&"
    assert environment["HOUDINI_SCRIPT_PATH"].split(os.pathsep)[-1] == "&"
    assert base == {"HOUDINI_PATH": "custom", "HOUDINI_SCRIPT_PATH": ""}


def test_render_with_husk_returns_failure_for_nonzero_exit(tmp_path: Path) -> None:
    render = _load_script("render_with_husk.py")
    process = SimpleNamespace(returncode=1, stdout="", stderr="delegate failed")

    with patch.object(render, "find_husk", return_value="husk"), patch.object(
        render.subprocess, "run", return_value=process
    ):
        result = render.render_with_husk(str(tmp_path / "scene.usda"), str(tmp_path / "beauty.exr"))

    assert result["success"] is False
    assert result["context"]["returncode"] == 1
    assert result["context"]["written_files"] == []
    assert "delegate failed" in result["error"]
