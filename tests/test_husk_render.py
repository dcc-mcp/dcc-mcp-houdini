"""Unit coverage for native Husk command and result contracts."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from skill_loader import skill_script_import_context

SCRIPTS = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills" / "houdini-husk" / "scripts"


def _load_script(filename: str):
    path = SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(f"husk_test_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_build_husk_command_resolves_karma_alias() -> None:
    common = _load_script("_husk_common.py")

    command = common.build_husk_command("scene.usda", "beauty.exr", renderer="karma")

    assert command[:3] == ["husk", "--renderer", "BRAY_HdKarma"]


def test_build_husk_command_clamps_single_frame() -> None:
    common = _load_script("_husk_common.py")

    command = common.build_husk_command("scene.usda", "beauty.exr", frame=8)

    assert command[command.index("--frame") : command.index("--frame") + 4] == [
        "--frame",
        "8",
        "--frame-count",
        "1",
    ]


def test_build_husk_command_converts_frame_range_to_husk_contract() -> None:
    common = _load_script("_husk_common.py")

    command = common.build_husk_command("scene.usda", "beauty.$F4.exr", frame_range=[1, 12, 2])

    assert command[command.index("--frame") : command.index("--frame") + 6] == [
        "--frame",
        "1.0",
        "--frame-count",
        "6",
        "--frame-inc",
        "2.0",
    ]


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


def test_render_with_husk_creates_parent_and_reports_single_frame_pattern(tmp_path: Path) -> None:
    render = _load_script("render_with_husk.py")
    output_pattern = tmp_path / "new" / "review" / "beauty.$F4.exr"
    expected_output = tmp_path / "new" / "review" / "beauty.0007.exr"
    process = SimpleNamespace(returncode=0, stdout="", stderr="")

    def run_husk(*_args, **_kwargs):
        assert output_pattern.parent.is_dir()
        expected_output.write_bytes(b"render")
        return process

    with patch.object(render, "find_husk", return_value="husk"), patch.object(
        render.subprocess, "run", side_effect=run_husk
    ):
        result = render.render_with_husk(
            str(tmp_path / "scene.usda"),
            str(output_pattern),
            frame=7,
        )

    assert result["success"] is True
    assert result["context"]["written_files"] == [str(expected_output)]


def test_render_with_husk_reports_frame_range_pattern(tmp_path: Path) -> None:
    render = _load_script("render_with_husk.py")
    output_pattern = tmp_path / "sequence" / "beauty.$F4.exr"
    expected_outputs = [output_pattern.parent / f"beauty.{frame:04d}.exr" for frame in (1, 3, 5)]
    process = SimpleNamespace(returncode=0, stdout="", stderr="")

    def run_husk(*_args, **_kwargs):
        for output in expected_outputs:
            output.write_bytes(b"render")
        return process

    with patch.object(render, "find_husk", return_value="husk"), patch.object(
        render.subprocess, "run", side_effect=run_husk
    ):
        result = render.render_with_husk(
            str(tmp_path / "scene.usda"),
            str(output_pattern),
            frame_range=[1, 5, 2],
        )

    assert result["success"] is True
    assert result["context"]["written_files"] == [str(output) for output in expected_outputs]


class _SnapshotParm:
    def __init__(self, rop, name: str) -> None:
        self.rop = rop
        self.name = name

    def set(self, value) -> None:
        self.rop.values[self.name] = value

    def pressButton(self) -> None:
        self.rop.executed = True
        if self.rop.write_output:
            output = self.rop.expanded_output or Path(self.rop.values["lopoutput"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("#usda 1.0\n", encoding="utf-8")


class _SnapshotRop:
    def __init__(self, write_output: bool, expanded_output=None) -> None:
        self.values = {}
        self.write_output = write_output
        self.expanded_output = expanded_output
        self.executed = False
        self.destroyed = False
        self.input = None

    def parm(self, name: str):
        return _SnapshotParm(self, name)

    def parmTuple(self, _name: str):
        return None

    def setInput(self, _index: int, source) -> None:
        self.input = source

    def destroy(self) -> None:
        self.destroyed = True


class _SnapshotParent:
    def __init__(self, write_output: bool, expanded_output=None) -> None:
        self.rop = _SnapshotRop(write_output, expanded_output)
        self.created_type = None

    def createNode(self, node_type: str, node_name: str):
        self.created_type = (node_type, node_name)
        return self.rop


class _SnapshotSource:
    def __init__(self, parent: _SnapshotParent) -> None:
        self._parent = parent

    def path(self) -> str:
        return "/stage/OUT"

    def parent(self) -> _SnapshotParent:
        return self._parent


class _SnapshotNetwork:
    def __init__(self, source: _SnapshotSource) -> None:
        self.source = source

    def path(self) -> str:
        return "/stage"

    def displayNode(self) -> _SnapshotSource:
        return self.source


@pytest.mark.parametrize(
    ("flatten", "save_style"),
    [(False, "flattenimplicitlayers"), (True, "flattenstage")],
)
def test_create_snapshot_uses_houdini21_usd_rop(tmp_path: Path, flatten: bool, save_style: str) -> None:
    snapshot = _load_script("create_snapshot.py")
    output = tmp_path / "cache" / "scene.0046.usda"
    raw_output = "$HIP/cache/scene.$F4.usda"
    parent = _SnapshotParent(write_output=True, expanded_output=output)
    source = _SnapshotSource(parent)
    hou = SimpleNamespace(
        node=lambda _path: _SnapshotNetwork(source),
        frame=lambda: 1.0,
        text=SimpleNamespace(
            expandStringAtFrame=lambda path, frame: str(output) if path == raw_output and frame == 46 else path
        ),
    )

    with patch.dict(sys.modules, {"hou": hou}):
        result = snapshot.create_snapshot(snapshot_path=raw_output, flatten=flatten, frame=46)

    assert result["success"] is True
    assert parent.created_type == ("usd_rop", "snapshot_export")
    assert parent.rop.input is source
    assert parent.rop.values["lopoutput"] == raw_output
    assert parent.rop.values["savestyle"] == save_style
    assert parent.rop.values["trange"] == 1
    assert parent.rop.values["f1"] == parent.rop.values["f2"] == 46.0
    assert parent.rop.executed is True
    assert parent.rop.destroyed is True
    assert output.is_file()
    assert result["context"]["expanded_snapshot_path"] == str(output)


def test_create_snapshot_fails_when_usd_rop_writes_nothing(tmp_path: Path) -> None:
    snapshot = _load_script("create_snapshot.py")
    parent = _SnapshotParent(write_output=False)
    source = _SnapshotSource(parent)
    output = tmp_path / "missing.usda"
    hou = SimpleNamespace(
        node=lambda _path: source,
        frame=lambda: 1.0,
        text=SimpleNamespace(expandStringAtFrame=lambda path, _frame: path),
    )

    with patch.dict(sys.modules, {"hou": hou}):
        result = snapshot.create_snapshot(source_path="/stage/locked_asset", snapshot_path=str(output))

    assert result["success"] is False
    assert parent.rop.input is source
    assert parent.rop.destroyed is True
