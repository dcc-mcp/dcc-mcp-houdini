"""Contracts for USD attribute writes in houdini-usd-lops."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-usd-lops"


def _load(name):
    spec = importlib.util.spec_from_file_location("usdwrite_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _Attribute:
    def __init__(self):
        self._value = None

    def Set(self, value, _time):
        self._value = value
        return True

    def Get(self, _time):
        return self._value


class _FailingAttribute(_Attribute):
    def Set(self, value, _time):
        return False


class _Prim:
    def __init__(self, fail_for=()):
        self.attributes = {}
        self.fail_for = fail_for

    def CreateAttribute(self, name, _type):
        attribute = _FailingAttribute() if name in self.fail_for else _Attribute()
        self.attributes[name] = attribute
        return attribute

    def GetAttribute(self, name):
        return self.attributes.get(name)


class _Stage:
    def __init__(self, prim, valid_path="/hero"):
        self._prim = prim
        self._valid_path = valid_path

    def GetPrimAtPath(self, path):
        return self._prim if path == self._valid_path else None


def _hou_with_stage(stage):
    node = SimpleNamespace(stage=lambda: stage)
    return SimpleNamespace(node=lambda path: node if path == "/stage/lopnet1" else None)


def _usd_modules():
    Usd = SimpleNamespace(TimeCode=SimpleNamespace(Default=lambda: "default"))
    Sdf = SimpleNamespace(
        ValueTypeNames=SimpleNamespace(
            Bool="bool", Int="int", Float="float", String="string", Float2="float2", Float3="float3"
        )
    )
    return Usd, Sdf


def test_set_prim_attributes_writes_and_reads_back():
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    Usd, Sdf = _usd_modules()
    with patch.dict(sys.modules, {"hou": hou, "Usd": Usd, "Sdf": Sdf}):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"density": 2.5, "label": "hero", "flag": True}
        )
    assert result["success"]
    context = result["context"]
    assert context["applied_attributes"] == {"density": 2.5, "label": "hero", "flag": True}
    assert context["attribute_readback"] == context["applied_attributes"]
    assert context["readback_matches"] is True
    assert context["skipped_parameters"] == []
    assert context["validation_scope"] == "stage_write_and_readback"


def test_set_prim_attributes_supports_vector_values():
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    Usd, Sdf = _usd_modules()
    with patch.dict(sys.modules, {"hou": hou, "Usd": Usd, "Sdf": Sdf}):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"center": [1.0, 2.0, 3.0], "uv": [0.0, 1.0]}
        )
    assert result["success"]
    assert result["context"]["applied_attributes"] == {"center": [1.0, 2.0, 3.0], "uv": [0.0, 1.0]}


def test_set_prim_attributes_reports_skipped_writes():
    prim = _Prim(fail_for=("density",))
    hou = _hou_with_stage(_Stage(prim))
    Usd, Sdf = _usd_modules()
    with patch.dict(sys.modules, {"hou": hou, "Usd": Usd, "Sdf": Sdf}):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", {"density": 2.5})
    assert result["success"]
    assert result["context"]["skipped_parameters"] == ["density"]
    assert result["context"]["applied_attributes"] == {}


def test_set_prim_attributes_rejects_unsupported_value_types():
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    Usd, Sdf = _usd_modules()
    with patch.dict(sys.modules, {"hou": hou, "Usd": Usd, "Sdf": Sdf}):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"nested": {"a": 1}, "ok": 1}
        )
    assert not result["success"]
    assert "Unsupported attribute value types" in skill_error_detail(result)


def test_set_prim_attributes_rejects_unknown_prim():
    hou = _hou_with_stage(_Stage(_Prim()))
    Usd, Sdf = _usd_modules()
    with patch.dict(sys.modules, {"hou": hou, "Usd": Usd, "Sdf": Sdf}):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/missing", {"a": 1})
    assert not result["success"]
    assert "USD prim not found" in skill_error_detail(result)


@pytest.mark.parametrize("attributes", [{}, None, "density"])
def test_set_prim_attributes_validates_attributes(attributes):
    hou = _hou_with_stage(_Stage(_Prim()))
    Usd, Sdf = _usd_modules()
    with patch.dict(sys.modules, {"hou": hou, "Usd": Usd, "Sdf": Sdf}):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", attributes)
    assert not result["success"]
    assert "attributes must be a non-empty object" in skill_error_detail(result)


def test_set_prim_attributes_rejects_invalid_names():
    hou = _hou_with_stage(_Stage(_Prim()))
    Usd, Sdf = _usd_modules()
    with patch.dict(sys.modules, {"hou": hou, "Usd": Usd, "Sdf": Sdf}):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", {"bad name!": 1})
    assert not result["success"]
    assert "Invalid USD attribute name" in skill_error_detail(result)


def test_set_prim_attributes_requires_usd():
    result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", {"a": 1})
    assert not result["success"]
    assert result["message"] == "Houdini not available"
