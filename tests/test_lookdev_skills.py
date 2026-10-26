"""Mock-hou unit tests for the houdini-lookdev skill."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-lookdev" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"lookdev_{path.stem}", path)
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


def _parm(name, value):
    parm = MagicMock()
    parm.name.return_value = name
    parm.eval.return_value = value
    return parm


class TestLookdevCoerceScalar:
    """Host-independent unit tests for the shared null-rejection contract."""

    @pytest.mark.parametrize("current", ["old", True, 3, 0.5])
    def test_coerce_scalar_rejects_null(self, current) -> None:
        # DEF-1/DEF-2: a null value must never be coerced to "None"/False/None;
        # it must fail with a TypeError so set_parameters records a structured
        # error instead of writing a host value and reporting success.
        common = _load_script("_lookdev_common.py")
        with pytest.raises(TypeError) as excinfo:
            common.coerce_scalar(None, current)
        assert "none" in str(excinfo.value).lower()

    def test_coerce_scalar_bool_string_parsing(self) -> None:
        # Copy-drift hardening: a string like "false"/"0" must not be coerced
        # truthily to True for a toggle parameter.
        common = _load_script("_lookdev_common.py")
        assert common.coerce_scalar("false", True) is False
        assert common.coerce_scalar("0", True) is False
        assert common.coerce_scalar("yes", True) is True
        assert common.coerce_scalar("1", True) is True


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
        tuple_parm = [MagicMock() for _ in range(3)]
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
        for component, value in zip(tuple_parm, (0.8, 0.4, 0.2)):
            component.set.assert_called_once_with(value, follow_parm_reference=False)
        scalar_parm.set.assert_called_once_with(0.6, follow_parm_reference=False)

    def test_set_material_parms_rejects_null_for_string_parm(self) -> None:
        # DEF-1: null must not become the literal "None" and must not be reported
        # as an applied, successful write; the host value must be left intact.
        mod = _load_script("set_material_parms.py")
        parm = MagicMock()
        parm.eval.return_value = "hello"
        node = _node("/mat/clay", "clay", "principledshader::2.0")
        node.parm.side_effect = lambda n: parm if n == "name" else None
        node.parmTuple.side_effect = lambda n: None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_material_parms("/mat/clay", {"name": None})
        assert result["success"] is False
        assert "name" in result["context"]["errors"]
        assert "none" in result["context"]["errors"]["name"].lower()
        parm.set.assert_not_called()
        assert "name" not in result["context"].get("applied", {})

    def test_set_material_parms_rejects_null_for_toggle_parm(self) -> None:
        # DEF-2: bool(None) would otherwise silently write False to a toggle.
        mod = _load_script("set_material_parms.py")
        parm = MagicMock()
        parm.eval.return_value = True
        node = _node("/mat/clay", "clay", "principledshader::2.0")
        node.parm.side_effect = lambda n: parm if n == "flag" else None
        node.parmTuple.side_effect = lambda n: None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_material_parms("/mat/clay", {"flag": None})
        assert result["success"] is False
        assert "flag" in result["context"]["errors"]
        parm.set.assert_not_called()
        assert "flag" not in result["context"].get("applied", {})

    def test_set_material_parms_rejects_null_for_int_parm(self) -> None:
        # Numeric null must fail cleanly with a readable error and no write.
        mod = _load_script("set_material_parms.py")
        parm = MagicMock()
        parm.eval.return_value = 3
        node = _node("/mat/clay", "clay", "principledshader::2.0")
        node.parm.side_effect = lambda n: parm if n == "count" else None
        node.parmTuple.side_effect = lambda n: None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_material_parms("/mat/clay", {"count": None})
        assert result["success"] is False
        assert "count" in result["context"]["errors"]
        assert "none" in result["context"]["errors"]["count"].lower()
        parm.set.assert_not_called()

    def test_set_material_parms_null_does_not_block_sibling_values(self) -> None:
        # A null value is reported per-parameter; a valid sibling still applies.
        mod = _load_script("set_material_parms.py")
        rough_parm = MagicMock()
        rough_parm.eval.return_value = 0.0
        str_parm = MagicMock()
        str_parm.eval.return_value = "hello"
        node = _node("/mat/clay", "clay", "principledshader::2.0")
        node.parmTuple.side_effect = lambda n: None
        node.parm.side_effect = lambda n: {"rough": rough_parm, "name": str_parm}.get(n)
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_material_parms("/mat/clay", {"rough": 0.6, "name": None})
        assert result["success"] is True
        rough_parm.set.assert_called_once_with(0.6, follow_parm_reference=False)
        str_parm.set.assert_not_called()
        assert result["context"]["applied"] == {"rough": 0.6}
        assert "name" in result["context"]["errors"]

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
        target_parm.set.assert_called_once_with(0.6, follow_parm_reference=False)

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

    def test_load_preset_reports_null_param_as_error(self, tmp_path: Path, monkeypatch) -> None:
        # A preset whose only value is null must surface a structured error and
        # must not report unconditional success; the host value stays intact.
        monkeypatch.setenv("DCC_MCP_HOUDINI_MATERIAL_PRESET_DIR", str(tmp_path))
        preset = {"material_type": "principledshader::2.0", "parameters": {"rough": None}}
        (tmp_path / "nullpreset.json").write_text(json.dumps(preset), encoding="utf-8")
        load_mod = _load_script("load_preset.py")
        target_parm = MagicMock()
        target_parm.eval.return_value = 0.0
        target = _node("/mat/clay2", "clay2", "principledshader::2.0")
        target.parmTuple.return_value = None
        target.parm.side_effect = lambda n: target_parm if n == "rough" else None
        load_hou = MagicMock()
        load_hou.node.return_value = target
        with patch.dict(sys.modules, {"hou": load_hou}):
            result = load_mod.load_preset("nullpreset", "/mat/clay2")
        assert result["success"] is False
        assert "rough" in result["context"]["errors"]
        target_parm.set.assert_not_called()
        assert "rough" not in result["context"].get("applied", {})

    def test_load_preset_null_does_not_block_sibling_values(self, tmp_path: Path, monkeypatch) -> None:
        # With a valid sibling present, load reports success, applies the valid
        # value, and surfaces the null parameter as a per-parameter error.
        monkeypatch.setenv("DCC_MCP_HOUDINI_MATERIAL_PRESET_DIR", str(tmp_path))
        preset = {"material_type": "principledshader::2.0", "parameters": {"rough": 0.6, "name": None}}
        (tmp_path / "mixed.json").write_text(json.dumps(preset), encoding="utf-8")
        load_mod = _load_script("load_preset.py")
        rough_parm = MagicMock()
        rough_parm.eval.return_value = 0.0
        str_parm = MagicMock()
        str_parm.eval.return_value = "hello"
        target = _node("/mat/clay2", "clay2", "principledshader::2.0")
        target.parmTuple.return_value = None
        target.parm.side_effect = lambda n: {"rough": rough_parm, "name": str_parm}.get(n)
        load_hou = MagicMock()
        load_hou.node.return_value = target
        with patch.dict(sys.modules, {"hou": load_hou}):
            result = load_mod.load_preset("mixed", "/mat/clay2")
        assert result["success"] is True
        rough_parm.set.assert_called_once_with(0.6, follow_parm_reference=False)
        str_parm.set.assert_not_called()
        assert result["context"]["applied"] == {"rough": 0.6}
        assert "name" in result["context"]["errors"]
