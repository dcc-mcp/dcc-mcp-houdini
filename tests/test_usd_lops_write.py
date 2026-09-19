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


class _Vec:
    """Stand-in for Gf.Vec2f / Gf.Vec3f."""

    def __init__(self, *values):
        self.values = tuple(values)

    def __eq__(self, other):
        return isinstance(other, _Vec) and other.values == self.values

    def __hash__(self):
        return hash(self.values)

    def __repr__(self):
        return "_Vec{}".format(self.values)


def _as_vec(values):
    return _Vec(*(float(item) for item in values))


class _Attribute:
    """Rejects anything USD would reject: vectors must arrive as Gf values."""

    VECTOR_TYPES = ("float2", "float3")

    def __init__(self, type_name):
        self.type_name = type_name
        self._value = None

    def Set(self, value, _time):
        if self.type_name in self.VECTOR_TYPES and not isinstance(value, _Vec):
            raise TypeError("{} expects a Gf value, got {!r}".format(self.type_name, type(value).__name__))
        self._value = value
        return True

    def Get(self, _time):
        return self._value


class _FailingAttribute(_Attribute):
    def Set(self, value, _time):
        return False


class _Prim:
    def __init__(self, fail_for=(), raise_for=()):
        self.attributes = {}
        self.fail_for = fail_for
        self.raise_for = raise_for

    def CreateAttribute(self, name, type_name):
        if name in self.raise_for:
            attribute = _Attribute(type_name)

            def boom(_value, _time):
                raise RuntimeError("stage refused the write")

            attribute.Set = boom
        else:
            attribute = _FailingAttribute(type_name) if name in self.fail_for else _Attribute(type_name)
        self.attributes[name] = attribute
        return attribute

    def RemoveProperty(self, name):
        self.attributes.pop(name, None)

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
    """USD doubles registered the way Houdini exposes them: as pxr.*."""
    Usd = SimpleNamespace(TimeCode=SimpleNamespace(Default=lambda: "default"))
    Sdf = SimpleNamespace(
        ValueTypeNames=SimpleNamespace(
            Bool="bool", Int="int", Float="float", String="string", Float2="float2", Float3="float3"
        )
    )
    Gf = SimpleNamespace(Vec2f=_Vec2f, Vec3f=_Vec3f)
    return Usd, Sdf, Gf


def _Vec2f(*values):
    return _as_vec(values)


def _Vec3f(*values):
    return _as_vec(values)


def _pxr_modules():
    """Module map for `from pxr import ...`, the only import shape Houdini supports."""
    Usd, Sdf, Gf = _usd_modules()
    return {
        "pxr": SimpleNamespace(Usd=Usd, Sdf=Sdf, Gf=Gf),
        "pxr.Usd": Usd,
        "pxr.Sdf": Sdf,
        "pxr.Gf": Gf,
    }


def test_set_prim_attributes_writes_and_reads_back():
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
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
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"center": [1.0, 2.0, 3.0], "uv": [0.0, 1.0]}
        )
    assert result["success"]
    context = result["context"]
    # USD stores vectors as Gf values, not the raw lists the caller supplied.
    assert context["applied_attributes"]["center"] == _as_vec([1.0, 2.0, 3.0])
    assert context["applied_attributes"]["uv"] == _as_vec([0.0, 1.0])
    assert context["readback_matches"] is True


def test_set_prim_attributes_removes_an_attribute_that_could_not_be_written():
    """A refused write must not leave an attribute holding a default value.

    An attribute that exists with a default reads as "written" to a caller who
    only checks that the name is present, so it is removed and reported.
    """
    prim = _Prim(fail_for=("density",))
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", {"density": 2.5})
    assert result["success"]
    assert result["context"]["skipped_parameters"] == ["density"]
    assert result["context"]["applied_attributes"] == {}
    assert prim.attributes == {}


def test_set_prim_attributes_keeps_earlier_writes_when_a_later_one_is_refused():
    """Only the refused attribute is removed; the successful ones stay."""
    prim = _Prim(fail_for=("density",))
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"label": "hero", "density": 2.5}
        )
    assert result["success"]
    assert result["context"]["skipped_parameters"] == ["density"]
    assert result["context"]["applied_attributes"] == {"label": "hero"}
    assert list(prim.attributes) == ["label"]


def test_set_prim_attributes_rejects_unsupported_value_types():
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"nested": {"a": 1}, "ok": 1}
        )
    assert not result["success"]
    assert "Unsupported value type for attribute: nested" in skill_error_detail(result)


def test_set_prim_attributes_rejects_unknown_prim():
    hou = _hou_with_stage(_Stage(_Prim()))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/missing", {"a": 1})
    assert not result["success"]
    assert "USD prim not found" in skill_error_detail(result)


@pytest.mark.parametrize("attributes", [{}, None, "density"])
def test_set_prim_attributes_validates_attributes(attributes):
    hou = _hou_with_stage(_Stage(_Prim()))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", attributes)
    assert not result["success"]
    assert "attributes must be a non-empty object" in skill_error_detail(result)


def test_set_prim_attributes_rejects_invalid_names():
    hou = _hou_with_stage(_Stage(_Prim()))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", {"bad name!": 1})
    assert not result["success"]
    assert "Invalid USD attribute name" in skill_error_detail(result)


def test_set_prim_attributes_requires_usd():
    result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", {"a": 1})
    assert not result["success"]
    assert result["message"] == "Houdini not available"


def test_set_prim_attributes_imports_usd_through_pxr():
    """Houdini exposes USD only as pxr.*; a bare `import Usd` would always fail.

    This pins the import shape so a regression cannot be hidden by a mock that
    registers the wrong module name.
    """
    source = (_ROOT / "scripts" / "set_prim_attributes.py").read_text(encoding="utf-8")
    assert "from pxr import" in source
    assert "\n    import Sdf" not in source
    assert "\n    import Usd" not in source
    assert "\n    import Gf" not in source


def test_set_prim_attributes_writes_nothing_when_one_entry_is_invalid():
    """Pre-validation: a rejected entry must not leave earlier writes on the stage."""
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"ok": 1, "nested": {"a": 1}}
        )
    assert not result["success"]
    # The valid entry must never have been created on the prim.
    assert "ok" not in prim.attributes
    assert prim.attributes == {}


def test_set_prim_attributes_writes_nothing_when_a_name_is_invalid():
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"ok": 1, "bad name!": 2}
        )
    assert not result["success"]
    assert prim.attributes == {}


def test_mixed_scalar_and_vector_write_succeeds_together():
    """Scalars and vectors in one call: both land, and readback matches."""
    prim = _Prim()
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1",
            "/hero",
            {"density": 2.5, "center": [1.0, 2.0, 3.0], "uv": [0.0, 1.0], "label": "hero"},
        )
    assert result["success"]
    context = result["context"]
    assert context["applied_attributes"]["density"] == 2.5
    assert context["applied_attributes"]["label"] == "hero"
    assert context["applied_attributes"]["center"] == _as_vec([1.0, 2.0, 3.0])
    assert context["applied_attributes"]["uv"] == _as_vec([0.0, 1.0])
    assert context["readback_matches"] is True
    assert context["skipped_parameters"] == []


def test_vector_write_rolls_back_when_a_later_scalar_is_refused():
    """A Set-time failure must undo the earlier writes, including vectors.

    Pre-validation cannot catch everything USD rejects at Set time, so the write
    loop has to leave the prim as it found it rather than half-written.
    """
    prim = _Prim(raise_for=("density",))
    hou = _hou_with_stage(_Stage(prim))
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/hero", {"center": [1.0, 2.0, 3.0], "density": 2.5}
        )
    assert not result["success"]
    assert "stage refused the write" in skill_error_detail(result)
    # The vector that was already written must be gone again.
    assert prim.attributes == {}


def test_vector_values_are_rejected_without_gf_conversion():
    """Guards the Gf conversion: a raw list must never reach Set for a vector type."""
    prim = _Prim()
    attribute = prim.CreateAttribute("center", "float3")
    with pytest.raises(TypeError, match="float3 expects a Gf value"):
        attribute.Set([1.0, 2.0, 3.0], "default")
