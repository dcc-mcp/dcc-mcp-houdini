"""Mock-hou unit tests for the houdini-pipeline skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-pipeline" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"pipeline_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _node(path: str, name: str, type_name: str = "geo") -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = type_name
    return node


def _file_parm(name: str, value: str) -> MagicMock:
    """A string parm whose template reports a FileReference string type."""
    parm = MagicMock()
    parm.name.return_value = name
    parm.eval.return_value = value
    template = MagicMock()
    template.type.return_value = "STRING_T"
    template.stringType.return_value = "FILE_REF"
    parm.parmTemplate.return_value = template
    return parm


def _mock_hou_with_file_parms() -> MagicMock:
    mock_hou = MagicMock()
    mock_hou.parmTemplateType.String = "STRING_T"
    mock_hou.stringParmType.FileReference = "FILE_REF"
    mock_hou.text.expandString.side_effect = lambda s: s
    return mock_hou


class TestProject:
    def test_set_project_missing_no_create(self, tmp_path) -> None:
        mod = _load_script("set_project.py")
        target = tmp_path / "does_not_exist"
        mock_hou = MagicMock()
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_project(str(target), create=False)
        assert result["success"] is False

    def test_set_project_creates(self, tmp_path) -> None:
        mod = _load_script("set_project.py")
        target = tmp_path / "showA" / "shot010"
        mock_hou = MagicMock()
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_project(str(target), create=True)
        assert result["success"] is True
        assert target.is_dir()
        mock_hou.putenv.assert_called_once()

    def test_get_project(self, tmp_path) -> None:
        mod = _load_script("get_project.py")
        mock_hou = MagicMock()
        mock_hou.getenv.side_effect = lambda k: str(tmp_path) if k == "JOB" else None
        mock_hou.hipFile.path.return_value = "/scenes/shot.hip"
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_project()
        assert result["success"] is True
        assert result["context"]["job_exists"] is True
        assert result["context"]["hip_file"] == "/scenes/shot.hip"


class TestMetadata:
    def test_tag_then_get_node_metadata(self) -> None:
        store: dict = {}
        node = _node("/obj", "obj", "obj")
        node.userData.side_effect = lambda k: store.get(k)
        node.setUserData.side_effect = lambda k, v: store.__setitem__(k, v)
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        tag_mod = _load_script("tag_asset_metadata.py")
        with patch.dict(sys.modules, {"hou": mock_hou}):
            tag_result = tag_mod.tag_asset_metadata({"shot": "sh010"}, node_path="/obj")
        assert tag_result["success"] is True
        assert "shot" in tag_result["context"]["keys"]

        get_mod = _load_script("get_asset_metadata.py")
        with patch.dict(sys.modules, {"hou": mock_hou}):
            get_result = get_mod.get_asset_metadata(node_path="/obj")
        assert get_result["success"] is True
        assert get_result["context"]["metadata"]["shot"] == "sh010"

    def test_tag_metadata_merges(self) -> None:
        store: dict = {}
        node = _node("/obj", "obj", "obj")
        node.userData.side_effect = lambda k: store.get(k)
        node.setUserData.side_effect = lambda k, v: store.__setitem__(k, v)
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        tag_mod = _load_script("tag_asset_metadata.py")
        with patch.dict(sys.modules, {"hou": mock_hou}):
            tag_mod.tag_asset_metadata({"a": 1}, node_path="/obj")
            result = tag_mod.tag_asset_metadata({"b": 2}, node_path="/obj", merge=True)
        assert set(result["context"]["keys"]) == {"a", "b"}

    def test_tag_rejects_empty(self) -> None:
        mod = _load_script("tag_asset_metadata.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.tag_asset_metadata({}, node_path="/obj")
        assert result["success"] is False


class TestValidation:
    def test_validate_scene_reports_missing(self, tmp_path) -> None:
        mod = _load_script("validate_scene.py")
        missing = str(tmp_path / "nope.bgeo")
        node = _node("/obj/geo1/file1", "file1", "file")
        node.parms.return_value = [_file_parm("file", missing)]
        node.errors.return_value = []
        mock_hou = _mock_hou_with_file_parms()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.validate_scene(node_paths=["/obj/geo1/file1"])
        assert result["success"] is True
        assert result["context"]["valid"] is False
        assert result["context"]["missing_files"][0]["path"] == missing

    def test_validate_scene_clean(self, tmp_path) -> None:
        mod = _load_script("validate_scene.py")
        existing = tmp_path / "in.bgeo"
        existing.write_text("x")
        node = _node("/obj/geo1/file1", "file1", "file")
        node.parms.return_value = [_file_parm("file", str(existing))]
        node.errors.return_value = []
        mock_hou = _mock_hou_with_file_parms()
        mock_hou.node.return_value = node
        mock_hou.hipFile.hasUnsavedChanges.return_value = False
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.validate_scene(node_paths=["/obj/geo1/file1"])
        assert result["context"]["valid"] is True
        assert result["context"]["dirty"] is False

    def test_collect_dependencies(self, tmp_path) -> None:
        mod = _load_script("collect_dependencies.py")
        existing = tmp_path / "tex.exr"
        existing.write_text("x")
        node = _node("/mat/tex", "tex", "texture")
        node.parms.return_value = [_file_parm("map", str(existing))]
        mock_hou = _mock_hou_with_file_parms()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.collect_dependencies(node_paths=["/mat/tex"])
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["missing_count"] == 0
        assert result["context"]["dependencies"][0]["exists"] is True


class TestPackage:
    def test_export_shot_package_manifest(self, tmp_path) -> None:
        mod = _load_script("export_shot_package.py")
        cam = _node("/obj/cam1", "cam1", "cam")
        rop = _node("/out/mantra1", "mantra1", "ifd")
        out_parm = _file_parm("vm_picture", str(tmp_path / "render.$F4.exr"))
        rop.parms.return_value = [out_parm]
        cam.parms.return_value = []
        root = MagicMock()
        root.allSubChildren.return_value = [cam, rop]
        mock_hou = _mock_hou_with_file_parms()
        mock_hou.node.side_effect = lambda p: root if p == "/" else None
        mock_hou.playbar.frameRange.return_value = (1.0, 24.0)
        mock_hou.fps.return_value = 24.0
        mock_hou.hipFile.path.return_value = "/scenes/shot.hip"

        out_json = tmp_path / "pkg" / "package.json"
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_shot_package(output_path=str(out_json), write_manifest=True)
        assert result["success"] is True
        manifest = result["context"]["manifest"]
        assert manifest["frame_range"] == [1.0, 24.0]
        assert manifest["fps"] == 24.0
        assert "/obj/cam1" in manifest["cameras"]
        assert "/out/mantra1" in manifest["output_nodes"]
        assert out_json.is_file()

    def test_export_requires_output_path_when_writing(self) -> None:
        mod = _load_script("export_shot_package.py")
        root = MagicMock()
        root.allSubChildren.return_value = []
        mock_hou = _mock_hou_with_file_parms()
        mock_hou.node.side_effect = lambda p: root if p == "/" else None
        mock_hou.playbar.frameRange.return_value = (1.0, 10.0)
        mock_hou.fps.return_value = 24.0
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_shot_package(write_manifest=True)
        assert result["success"] is False
