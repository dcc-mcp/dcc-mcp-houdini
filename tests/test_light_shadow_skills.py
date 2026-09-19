"""Public domain tool contracts for per-light shadow configuration."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from domain_graph_fakes import Parm, scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-light-rig"


def _load(name):
    spec = importlib.util.spec_from_file_location("lightshadow_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _light(root, name="key_light"):
    return root.createNode("hlight", name)


def test_configure_light_shadow_applies_first_matching_alias():
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["shadowenable"] = Parm("shadowenable", 0)
    light.parms["vm_shadowquality"] = Parm("vm_shadowquality", 1)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_light_shadow.py").configure_light_shadow(light.path(), {"enable": 1, "quality": 4})
    assert result["success"]
    context = result["context"]
    assert context["applied_parameters"] == {"shadowenable": 1, "vm_shadowquality": 4}
    assert context["skipped_parameters"] == []
    assert context["resolved_names"] == {"enable": "shadowenable", "quality": "vm_shadowquality"}
    assert light.parm("shadowenable").eval() == 1


def test_configure_light_shadow_reports_skipped_parameters():
    root, _geo, hou = scene()
    light = _light(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_light_shadow.py").configure_light_shadow(light.path(), {"bias": 0.01})
    assert result["success"]
    context = result["context"]
    assert context["applied_parameters"] == {}
    assert context["skipped_parameters"] == ["bias"]
    assert context["resolved_names"] == {"bias": None}
    assert context["validation_scope"] == "parameter_presence"


def test_configure_light_shadow_mixes_applied_and_unsupported():
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["shadowblur"] = Parm("shadowblur", 0)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_light_shadow.py").configure_light_shadow(
            light.path(), {"softness": 0.5, "distance": 12}
        )
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"shadowblur": 0.5}
    assert result["context"]["skipped_parameters"] == ["distance"]


def test_configure_light_shadow_rejects_unknown_setting_name():
    root, _geo, hou = scene()
    light = _light(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_light_shadow.py").configure_light_shadow(light.path(), {"penumbra": 0.5})
    assert not result["success"]
    assert "Unsupported shadow settings" in skill_error_detail(result)


def test_configure_light_shadow_rolls_back_on_failed_write():
    root, _geo, hou = scene()
    light = _light(root)
    parm = Parm("shadowenable", 0)
    light.parms["shadowenable"] = parm
    light.parms["vm_shadowquality"] = Parm("vm_shadowquality", 1)
    light.parms["vm_shadowquality"].fail_next_set = True
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_light_shadow.py").configure_light_shadow(light.path(), {"enable": 1, "quality": 8})
    assert not result["success"]
    assert parm.eval() == 0


@pytest.mark.parametrize("settings", [{}, "softness", None])
def test_configure_light_shadow_validates_settings(settings):
    root, _geo, hou = scene()
    light = _light(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_light_shadow.py").configure_light_shadow(light.path(), settings)
    assert not result["success"]
    assert "settings must be a non-empty object" in skill_error_detail(result)


def test_hou_missing_returns_structured_error():
    root, _geo, _hou = scene()
    assert "hou" not in sys.modules
    result = _load("configure_light_shadow.py").configure_light_shadow("/obj/key_light", {"enable": 1})
    assert not result["success"]
    assert result["message"] == "Houdini not available"


def test_supported_settings_cover_all_documented_keys() -> None:
    module = _load("configure_light_shadow.py")
    assert set(module.SHADOW_PARM_ALIASES) == {
        "enable",
        "type",
        "quality",
        "softness",
        "samples",
        "distance",
        "bias",
        "color",
    }
