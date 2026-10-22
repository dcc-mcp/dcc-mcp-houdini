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


class _NotEditableError(RuntimeError):
    """Stands in for pxr's Tf.ErrorException raised against a read-only edit target."""


class _Layer:
    """A USD layer whose editability the tests control explicitly.

    OpenUSD exposes layer edit permission as the ``permissionToEdit`` property,
    not a ``PermissionToEdit()`` method; mirroring that keeps the doubles honest.
    """

    def __init__(self, identifier, editable):
        self.identifier = identifier
        self._editable = editable

    @property
    def permissionToEdit(self):
        return self._editable

    def __repr__(self):
        return "_Layer({!r}, editable={!r})".format(self.identifier, self._editable)


class _EditTarget:
    """A ``Usd.EditTarget`` double wrapping a single layer."""

    def __init__(self, layer):
        self._layer = layer

    def IsValid(self):
        return self._layer is not None

    def GetLayer(self):
        return self._layer


class _Prim:
    def __init__(self, fail_for=(), raise_for=(), stage=None):
        self.attributes = {}
        self.fail_for = fail_for
        self.raise_for = raise_for
        self.stage = stage

    def _current_layer(self):
        if self.stage is None:
            return None
        target = self.stage.GetEditTarget()
        if target is None or not target.IsValid():
            return None
        return target.GetLayer()

    def _assert_editable(self, action, name):
        # Doubles built without a stage (read-tool contracts) stay editable.
        if self.stage is None:
            return
        layer = self._current_layer()
        if layer is None or not layer.permissionToEdit:
            identifier = getattr(layer, "identifier", "anon")
            raise _NotEditableError(
                "Cannot {} spec at </World/{}>. Layer @{}@ is not editable".format(action, name, identifier)
            )

    def CreateAttribute(self, name, type_name):
        self._assert_editable("create", name)
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
        self._assert_editable("remove", name)
        self.attributes.pop(name, None)

    def GetAttribute(self, name):
        return self.attributes.get(name)


_UNSET = object()


class _Stage:
    def __init__(self, prim, valid_path="/hero", edit_target=_UNSET, session_layer=_UNSET):
        self._prim = prim
        self._valid_path = valid_path
        # Default to an already-editable edit target (an editable LOP) so the
        # original write contracts keep their behavior.
        self._session_layer = _Layer("@session@", editable=True) if session_layer is _UNSET else session_layer
        self._edit_target = (
            _EditTarget(_Layer("@editable:LOP@", editable=True)) if edit_target is _UNSET else edit_target
        )
        self.edit_target_history = [self._edit_target]
        if prim is not None:
            prim.stage = self

    def GetPrimAtPath(self, path):
        return self._prim if path == self._valid_path else None

    def GetEditTarget(self):
        return self._edit_target

    def SetEditTarget(self, target):
        self._edit_target = target
        self.edit_target_history.append(target)

    def GetSessionLayer(self):
        return self._session_layer


def _hou_with_stage(stage):
    node = SimpleNamespace(stage=lambda: stage)
    return SimpleNamespace(node=lambda path: node if path == "/stage/lopnet1" else None)


def _usd_modules():
    """USD doubles registered the way Houdini exposes them: as pxr.*."""
    Usd = SimpleNamespace(
        TimeCode=SimpleNamespace(Default=lambda: "default"),
        EditTarget=_EditTarget,
    )
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


# ---------------------------------------------------------------------------
# DEF-1: sublayer/reference prims live under a read-only edit target.
# node.stage() points at an anonymous "@anon:...:LOP@" layer that USD refuses to
# author, so the tool must retarget to the (always-writable) session layer.
# ---------------------------------------------------------------------------
def _sublayer_stage(prim):
    """A LOP stage whose default edit target is a read-only anonymous LOP layer.

    Models sublayer/reference content: authoring against the default target raises
    "not editable", exactly as a real Houdini LOP stage does for file-layer prims.
    """
    read_only = _Layer("@anon:0x0001:LOP@", editable=False)
    return _Stage(prim, valid_path="/World/geo/cube", edit_target=_EditTarget(read_only))


def test_set_prim_attributes_writes_a_sublayer_prim_through_the_session_layer():
    """DEF-1: a file-layer (sublayer/reference) prim must accept the write.

    The default edit target is read-only, so the tool retargets to the session
    layer, authors there, and reads the composed value back.
    """
    prim = _Prim()
    stage = _sublayer_stage(prim)
    hou = _hou_with_stage(stage)
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/World/geo/cube", {"p77_density": 2.5, "p77_label": "hero"}
        )
    assert result["success"], result
    context = result["context"]
    assert context["applied_attributes"] == {"p77_density": 2.5, "p77_label": "hero"}
    assert context["attribute_readback"] == context["applied_attributes"]
    assert context["readback_matches"] is True
    assert context["skipped_parameters"] == []


def test_set_prim_attributes_restores_the_original_edit_target_after_a_sublayer_write():
    """A write must not leave the shared stage pointing at the session layer."""
    prim = _Prim()
    read_only = _Layer("@anon:0x0001:LOP@", editable=False)
    stage = _Stage(prim, valid_path="/World/geo/cube", edit_target=_EditTarget(read_only))
    hou = _hou_with_stage(stage)
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/World/geo/cube", {"density": 1.0}
        )
    assert result["success"], result
    # Retargeted once for the write, then put back to what the caller had.
    assert len(stage.edit_target_history) >= 2
    assert stage.GetEditTarget().GetLayer() is read_only


def test_set_prim_attributes_leaves_an_editable_edit_target_in_place():
    """An already-writable target is never swapped for the session layer.

    Authoring on an editable LOP keeps using the node's own layer, so the edit
    target is left exactly as it was found.
    """
    prim = _Prim()
    stage = _Stage(prim)  # default: editable edit target
    hou = _hou_with_stage(stage)
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes("/stage/lopnet1", "/hero", {"density": 2.5})
    assert result["success"], result
    assert stage.edit_target_history == [stage.GetEditTarget()]


def test_set_prim_attributes_rolls_back_a_session_write_that_is_refused():
    """Rollback must still work while retargeted to the session layer.

    If the edit target were restored before rollback, RemoveProperty would hit the
    read-only layer and the earlier write would be silently left behind.
    """
    prim = _Prim(raise_for=("density",))
    stage = _sublayer_stage(prim)
    hou = _hou_with_stage(stage)
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/World/geo/cube", {"center": [1.0, 2.0, 3.0], "density": 2.5}
        )
    assert not result["success"]
    assert "stage refused the write" in skill_error_detail(result)
    assert prim.attributes == {}


def test_set_prim_attributes_reports_a_stage_without_a_writable_target():
    """No session layer and a read-only target: a clear structured failure."""
    prim = _Prim()
    read_only = _Layer("@anon:0x0001:LOP@", editable=False)
    stage = _Stage(prim, valid_path="/World/geo/cube", edit_target=_EditTarget(read_only), session_layer=None)
    hou = _hou_with_stage(stage)
    with patch.dict(sys.modules, dict(_pxr_modules(), hou=hou)):
        result = _load("set_prim_attributes.py").set_prim_attributes(
            "/stage/lopnet1", "/World/geo/cube", {"density": 2.5}
        )
    assert not result["success"]
    assert "session layer" in skill_error_detail(result)
    assert prim.attributes == {}
