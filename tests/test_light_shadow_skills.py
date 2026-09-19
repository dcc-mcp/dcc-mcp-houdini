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
    # Assert the conclusive field, not just the details: a partial configuration
    # is not valid, and a hardcoded valid=True survived here until it was caught.
    assert result["context"]["valid"] is False


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


# ---------------------------------------------------------------------------
# configure_light_bank / set_light_ies
# ---------------------------------------------------------------------------


def _load_script(name):
    spec = importlib.util.spec_from_file_location("lightrig_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _light(root, name="key_light"):
    return root.createNode("hlight", name)


def test_configure_light_bank_applies_categories():
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["categories"] = Parm("categories", "old")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("configure_light_bank.py").configure_light_bank(light.path(), {"categories": "hero rim"})
    assert result["success"]
    context = result["context"]
    assert context["applied_parameters"] == {"categories": "hero rim"}
    assert context["resolved_names"] == {"categories": "categories"}
    assert context["skipped_parameters"] == []
    # Found versus applied is reported separately.
    assert context["found_categories"] == "old"
    assert context["applied_categories"] == "hero rim"
    assert context["setup_state"] == "configured"
    assert context["required_setup"]
    assert light.parm("categories").eval() == "hero rim"


def test_configure_light_bank_reports_unchanged_when_light_exposes_nothing():
    root, _geo, hou = scene()
    light = _light(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("configure_light_bank.py").configure_light_bank(light.path(), {"categories": "hero"})
    assert result["success"]
    context = result["context"]
    assert context["applied_parameters"] == {}
    assert context["skipped_parameters"] == ["categories"]
    assert context["found_categories"] is None
    assert context["setup_state"] == "unchanged"
    assert context["valid"] is False


def test_configure_light_bank_mixes_applied_and_skipped():
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["categories"] = Parm("categories", "")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("configure_light_bank.py").configure_light_bank(
            light.path(), {"categories": "hero", "selectable": True}
        )
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"categories": "hero"}
    assert result["context"]["skipped_parameters"] == ["selectable"]
    assert result["context"]["valid"] is False


@pytest.mark.parametrize("settings", [{"nonsense": 1}, {}, None, "categories"])
def test_configure_light_bank_validates_settings(settings):
    root, _geo, hou = scene()
    light = _light(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("configure_light_bank.py").configure_light_bank(light.path(), settings)
    assert not result["success"]
    detail = skill_error_detail(result)
    assert "Unsupported light bank settings" in detail or "settings must be a non-empty object" in detail


def test_configure_light_bank_rolls_back_on_failed_write():
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["categories"] = Parm("categories", "original")
    light.parms["selectable"] = Parm("selectable", 1)
    light.parms["selectable"].fail_next_set = True
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("configure_light_bank.py").configure_light_bank(
            light.path(), {"categories": "hero", "selectable": False}
        )
    assert not result["success"]
    assert light.parm("categories").eval() == "original"


def test_set_light_ies_binds_an_existing_file(tmp_path):
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["iesfile"] = Parm("iesfile", "")
    profile = tmp_path / "profile.ies"
    profile.write_bytes(b"IES")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("set_light_ies.py").set_light_ies(light.path(), str(profile))
    assert result["success"]
    context = result["context"]
    assert context["ies_file_exists"] is True
    assert context["ies_state"] == "resolved"
    assert context["ies_bound"] is True
    assert context["applied_parameters"] == {"iesfile": str(profile)}
    assert context["setup_state"] == "configured"


def test_set_light_ies_does_not_claim_a_missing_file_is_bound(tmp_path):
    """A path that does not resolve must never be reported as bound."""
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["iesfile"] = Parm("iesfile", "")
    missing = str(tmp_path / "absent.ies")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("set_light_ies.py").set_light_ies(light.path(), missing)
    assert result["success"]
    context = result["context"]
    assert context["ies_file_exists"] is False
    assert context["ies_state"] == "missing"
    assert context["ies_bound"] is False
    assert light.parm("iesfile").eval() == missing


def test_set_light_ies_reports_unresolved_when_light_has_no_parameter(tmp_path):
    root, _geo, hou = scene()
    light = _light(root)
    profile = tmp_path / "profile.ies"
    profile.write_bytes(b"IES")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("set_light_ies.py").set_light_ies(light.path(), str(profile))
    assert result["success"]
    context = result["context"]
    assert context["ies_state"] == "unresolved"
    assert context["ies_bound"] is False
    assert context["skipped_parameters"] == ["ies_file"]
    assert context["setup_state"] == "unchanged"
    assert context["valid"] is False


def test_set_light_ies_expands_houdini_variables(tmp_path):
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["iesfile"] = Parm("iesfile", "")
    (tmp_path / "hip.ies").write_bytes(b"IES")
    hou.expandString = lambda value: value.replace("$HIP", str(tmp_path))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("set_light_ies.py").set_light_ies(light.path(), "$HIP/hip.ies")
    assert result["success"]
    assert result["context"]["ies_file_exists"] is True
    assert result["context"]["ies_state"] == "resolved"
    assert result["context"]["expanded_ies_file"].endswith("hip.ies")


def test_set_light_ies_applies_optional_settings(tmp_path):
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["iesfile"] = Parm("iesfile", "")
    light.parms["iesscale"] = Parm("iesscale", 1)
    profile = tmp_path / "profile.ies"
    profile.write_bytes(b"IES")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("set_light_ies.py").set_light_ies(light.path(), str(profile), {"ies_scale": 2.0})
    assert result["success"]
    assert result["context"]["applied_parameters"]["iesscale"] == 2.0
    assert result["context"]["skipped_parameters"] == []


@pytest.mark.parametrize("ies_file", ["", None, 5])
def test_set_light_ies_validates_the_path(ies_file):
    root, _geo, hou = scene()
    light = _light(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("set_light_ies.py").set_light_ies(light.path(), ies_file)
    assert not result["success"]
    assert "ies_file must be a non-empty string" in skill_error_detail(result)


def test_set_light_ies_rejects_unknown_settings(tmp_path):
    root, _geo, hou = scene()
    light = _light(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_script("set_light_ies.py").set_light_ies(light.path(), "/ies/a.ies", {"ies_color": "red"})
    assert not result["success"]
    assert "Unsupported IES settings" in skill_error_detail(result)


def test_new_light_tools_never_claim_render_verification(tmp_path):
    """No field may imply a render was verified."""
    root, _geo, hou = scene()
    light = _light(root)
    light.parms["categories"] = Parm("categories", "")
    light.parms["iesfile"] = Parm("iesfile", "")
    profile = tmp_path / "profile.ies"
    profile.write_bytes(b"IES")
    with patch.dict(sys.modules, {"hou": hou}):
        bank = _load_script("configure_light_bank.py").configure_light_bank(light.path(), {"categories": "hero"})
        ies = _load_script("set_light_ies.py").set_light_ies(light.path(), str(profile))
    for context in (bank["context"], ies["context"]):
        assert "render_verified" not in context
        assert "simulation_verified" not in context
        assert "setup_state" in context
        assert "required_setup" in context


def test_light_bank_and_ies_hou_missing():
    root, _geo, _hou = scene()
    assert "hou" not in sys.modules
    bank = _load_script("configure_light_bank.py").configure_light_bank("/obj/l", {"categories": "a"})
    ies = _load_script("set_light_ies.py").set_light_ies("/obj/l", "/ies/a.ies")
    for result in (bank, ies):
        assert not result["success"]
        assert result["message"] == "Houdini not available"
