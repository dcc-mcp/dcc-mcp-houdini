"""Mock-hou unit tests for the houdini-lookdev skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-lookdev" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"lookdev_{path.stem}", path)
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


def _parm(name, value):
    parm = MagicMock()
    parm.name.return_value = name
    parm.eval.return_value = value
    return parm


class TestLookdevQuery:
    def test_list_materials(self) -> None:
        mod = _load_script("list_materials.py")
        clay = _node("/mat/clay", "clay", "principledshader::2.0")
        clay.type.return_value.category.return_value.name.return_value = "Vop"
        parent = _node("/mat", "mat", "matnet")
        parent.children.return_value = [clay]
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_materials("/mat")
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["materials"][0]["name"] == "clay"

    def test_list_assignments(self) -> None:
        mod = _load_script("list_assignments.py")
        geo = _node("/obj/geo1", "geo1", "geo")
        geo.parm.side_effect = lambda n: _parm(n, "/mat/clay") if n == "shop_materialpath" else None
        empty = _node("/obj/geo2", "geo2", "geo")
        empty.parm.side_effect = lambda n: _parm(n, "") if n == "shop_materialpath" else None
        parent = _node("/obj", "obj")
        parent.children.return_value = [geo, empty]
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_assignments("/obj")
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["assignments"][0]["material"] == "/mat/clay"

    def test_get_material_parms_filter(self) -> None:
        mod = _load_script("get_material_parms.py")
        node = _node("/mat/clay", "clay", "principledshader::2.0")
        node.parms.return_value = [_parm("basecolorr", 0.8), _parm("rough", 0.5)]
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_material_parms("/mat/clay", name_filter="rough")
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["parameters"][0]["name"] == "rough"

    def test_get_shader_connections(self) -> None:
        mod = _load_script("get_shader_connections.py")
        src = _node("/mat/clay/tex", "tex", "texture")
        node = _node("/mat/clay/surface", "surface", "principledshader")
        node.inputNames.return_value = ["basecolor", "rough"]
        node.inputs.return_value = [src, None]
        node.outputs.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_shader_connections("/mat/clay/surface")
        assert result["success"] is True
        assert result["context"]["inputs"][0]["name"] == "basecolor"
        assert result["context"]["inputs"][0]["source"] == "/mat/clay/tex"
        assert result["context"]["inputs"][1]["source"] is None


class TestLookdevEdit:
    def test_set_material_parms_coerces(self) -> None:
        mod = _load_script("set_material_parms.py")
        tuple_parm = MagicMock()
        scalar_parm = MagicMock()
        scalar_parm.eval.return_value = 0.0
        node = _node("/mat/clay", "clay", "principledshader::2.0")
        node.parmTuple.side_effect = lambda n: tuple_parm if n == "basecolor" else None
        node.parm.side_effect = lambda n: scalar_parm if n == "rough" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_material_parms("/mat/clay", {"basecolor": [0.8, 0.4, 0.2], "rough": 0.6})
        assert result["success"] is True
        tuple_parm.set.assert_called_once_with((0.8, 0.4, 0.2))
        scalar_parm.set.assert_called_once_with(0.6)

    def test_connect_shader_by_name(self) -> None:
        mod = _load_script("connect_shader.py")
        node = _node("/mat/clay/surface", "surface", "principledshader")
        node.inputNames.return_value = ["basecolor", "rough"]
        src = _node("/mat/clay/tex", "tex", "texture")
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/mat/clay/surface": node,
            "/mat/clay/tex": src,
        }[p]
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.connect_shader("/mat/clay/surface", "/mat/clay/tex", input_name="rough")
        assert result["success"] is True
        node.setInput.assert_called_once_with(1, src, 0)

    def test_disconnect_shader(self) -> None:
        mod = _load_script("disconnect_shader.py")
        src = _node("/mat/clay/tex", "tex", "texture")
        node = _node("/mat/clay/surface", "surface", "principledshader")
        node.inputs.return_value = [src]
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.disconnect_shader("/mat/clay/surface", 0)
        assert result["success"] is True
        node.setInput.assert_called_once_with(0, None)
        assert result["context"]["previous_source"] == "/mat/clay/tex"

    def test_reset_material(self) -> None:
        mod = _load_script("reset_material.py")
        parm = MagicMock()
        geo = _node("/obj/geo1", "geo1", "geo")
        geo.parm.side_effect = lambda n: parm if n == "shop_materialpath" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = geo
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.reset_material(["/obj/geo1"])
        assert result["success"] is True
        parm.set.assert_called_once_with("")
        assert result["context"]["affected"] == ["/obj/geo1"]


class TestPresets:
    def test_save_list_load_delete_roundtrip(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("DCC_MCP_HOUDINI_MATERIAL_PRESET_DIR", str(tmp_path))

        save_mod = _load_script("save_preset.py")
        parm = _parm("rough", 0.6)
        node = _node("/mat/clay", "clay", "principledshader::2.0")
        node.parms.return_value = [parm]
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            save_result = save_mod.save_preset("/mat/clay", "warm_clay")
        assert save_result["success"] is True

        list_mod = _load_script("list_presets.py")
        list_result = list_mod.list_presets()
        assert list_result["success"] is True
        assert list_result["context"]["count"] == 1
        assert list_result["context"]["presets"][0]["material_type"] == "principledshader::2.0"

        load_mod = _load_script("load_preset.py")
        target_parm = MagicMock()
        target_parm.eval.return_value = 0.0
        target = _node("/mat/clay2", "clay2", "principledshader::2.0")
        target.parmTuple.return_value = None
        target.parm.side_effect = lambda n: target_parm if n == "rough" else None
        load_hou = MagicMock()
        load_hou.node.return_value = target
        with patch.dict(sys.modules, {"hou": load_hou}):
            load_result = load_mod.load_preset("warm_clay", "/mat/clay2")
        assert load_result["success"] is True
        target_parm.set.assert_called_once_with(0.6)

        delete_mod = _load_script("delete_preset.py")
        delete_result = delete_mod.delete_preset("warm_clay")
        assert delete_result["success"] is True
        assert list_mod.list_presets()["context"]["count"] == 0

    def test_load_missing_preset_errors(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("DCC_MCP_HOUDINI_MATERIAL_PRESET_DIR", str(tmp_path))
        load_mod = _load_script("load_preset.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = load_mod.load_preset("nope", "/mat/clay")
        assert result["success"] is False
