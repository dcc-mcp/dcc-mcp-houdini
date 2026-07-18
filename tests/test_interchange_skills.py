"""Mock-hou unit tests for the houdini-interchange skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-interchange" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"interchange_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _node(path: str, name: str, type_name: str = "geo") -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = type_name
    return node


class TestProbeFile:
    def test_existing_geometry_file(self, tmp_path: Path) -> None:
        mod = _load_script("probe_file.py")
        f = tmp_path / "cache.bgeo"
        f.write_bytes(b"data")
        result = mod.probe_file(str(f))
        assert result["success"] is True
        assert result["context"]["exists"] is True
        assert result["context"]["format"] == "geometry"
        assert result["context"]["is_supported_import"] is True
        assert result["context"]["size_bytes"] == 4

    def test_missing_file(self, tmp_path: Path) -> None:
        mod = _load_script("probe_file.py")
        result = mod.probe_file(str(tmp_path / "nope.usd"))
        assert result["success"] is True
        assert result["context"]["exists"] is False
        assert result["context"]["format"] == "usd"


class TestImportGeometry:
    def test_import_sets_file_parm(self, tmp_path: Path) -> None:
        mod = _load_script("import_geometry.py")
        src = tmp_path / "asset.obj"
        src.write_text("o", encoding="utf-8")
        file_parm = MagicMock()
        node = _node("/obj/geo1/file1", "file1", "file")
        node.parmTuple.return_value = None
        node.parm.side_effect = lambda n: file_parm if n == "file" else None
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = node
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.import_geometry("/obj/geo1", str(src), cook=False)

        assert result["success"] is True
        file_parm.set.assert_called_once_with(str(src))
        assert result["context"]["format"] == "obj"

    def test_missing_file_errors(self, tmp_path: Path) -> None:
        mod = _load_script("import_geometry.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.import_geometry("/obj/geo1", str(tmp_path / "absent.abc"))
        assert result["success"] is False

    def test_unsupported_format_errors(self, tmp_path: Path) -> None:
        mod = _load_script("import_geometry.py")
        src = tmp_path / "notes.txt"
        src.write_text("x", encoding="utf-8")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.import_geometry("/obj/geo1", str(src))
        assert result["success"] is False


class TestExportGeometry:
    def test_export_writes_file(self, tmp_path: Path) -> None:
        mod = _load_script("export_geometry.py")
        out = tmp_path / "out" / "box.bgeo"
        geo = MagicMock()
        geo.saveToFile.side_effect = lambda p: Path(p).write_bytes(b"geo")
        node = _node("/obj/geo1/box1", "box1", "box")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_geometry("/obj/geo1/box1", str(out))

        assert result["success"] is True
        geo.saveToFile.assert_called_once_with(str(out))
        assert result["context"]["written_files"] == [str(out)]
        assert result["context"]["skipped"] == []
        assert result["context"]["format"] == "geometry"


class TestExportAlembic:
    def test_export_configures_rop_without_render(self, tmp_path: Path) -> None:
        mod = _load_script("export_alembic.py")
        out = tmp_path / "cache.abc"
        filename_parm = MagicMock()
        rop = _node("/obj/geo1/abc_export", "abc_export", "rop_alembic")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: filename_parm if n == "filename" else None
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = rop
        source = _node("/obj/geo1/box1", "box1", "box")
        source.parent.return_value = parent
        mock_hou = MagicMock()
        mock_hou.node.return_value = source

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_alembic("/obj/geo1/box1", str(out), render=False)

        assert result["success"] is True
        filename_parm.set.assert_called_once_with(str(out))
        rop.setInput.assert_called_once_with(0, source)
        assert result["context"]["written_files"] == []
        assert result["context"]["skipped"] == [str(out)]

    def test_export_renders_and_reports_written(self, tmp_path: Path) -> None:
        mod = _load_script("export_alembic.py")
        out = tmp_path / "cache.abc"
        filename_parm = MagicMock()
        rop = _node("/obj/geo1/abc_export", "abc_export", "rop_alembic")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: filename_parm if n == "filename" else None
        rop.render.side_effect = lambda: out.write_bytes(b"abc")
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = rop
        source = _node("/obj/geo1/box1", "box1", "box")
        source.parent.return_value = parent
        mock_hou = MagicMock()
        mock_hou.node.return_value = source

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_alembic("/obj/geo1/box1", str(out), frame_range=[1, 10], render=True)

        assert result["success"] is True
        rop.render.assert_called_once()
        assert result["context"]["written_files"] == [str(out)]
        assert result["context"]["frame_range"] == [1.0, 10.0]


class TestExportFbx:
    def test_export_configures_fbx_rop(self, tmp_path: Path) -> None:
        mod = _load_script("export_fbx.py")
        out = tmp_path / "scene.fbx"
        sopoutput = MagicMock()
        startnode = MagicMock()
        rop = _node("/out/fbx_export", "fbx_export", "filmboxfbx")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: {"sopoutput": sopoutput, "startnode": startnode}.get(n)
        out_net = _node("/out", "out", "ropnet")
        out_net.createNode.return_value = rop
        obj = _node("/obj", "obj")
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {"/out": out_net, "/obj": obj}.get(p)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_fbx(str(out), root_node="/obj", render=False)

        assert result["success"] is True
        sopoutput.set.assert_called_once_with(str(out))
        startnode.set.assert_called_once_with("/obj")
        assert result["context"]["skipped"] == [str(out)]


class TestExportUsd:
    def test_export_reports_root_layer_and_written(self, tmp_path: Path) -> None:
        mod = _load_script("export_usd.py")
        out = tmp_path / "stage.usd"
        layer = MagicMock()
        layer.identifier = "stage.usd"
        stage = MagicMock()
        stage.GetRootLayer.return_value = layer
        stage.Export.side_effect = lambda p: Path(p).write_text("#usda 1.0", encoding="utf-8")
        node = _node("/stage/out", "out", "usd_rop")
        node.stage.return_value = stage
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_usd("/stage/out", str(out))

        assert result["success"] is True
        stage.Export.assert_called_once_with(str(out))
        assert result["context"]["root_layer"] == "stage.usd"
        assert result["context"]["written_files"] == [str(out)]

    def test_non_lop_node_errors(self) -> None:
        mod = _load_script("export_usd.py")
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        del node.stage  # no stage() method -> not a LOP node
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_usd("/obj/geo1", "/tmp/x.usd")

        assert result["success"] is False
