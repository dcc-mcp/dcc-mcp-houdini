"""Unit contracts for the USD stage-authoring edit-target helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-usd-lops"


def _load_common():
    spec = importlib.util.spec_from_file_location("usd_common_edit_target", _ROOT / "scripts" / "_usd_common.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _Layer:
    def __init__(self, identifier, editable):
        self.identifier = identifier
        self._editable = editable

    @property
    def permissionToEdit(self):
        # Real OpenUSD exposes this as a property, not a PermissionToEdit() call.
        return self._editable


class _EditTarget:
    def __init__(self, layer):
        self._layer = layer

    def IsValid(self):
        return self._layer is not None

    def GetLayer(self):
        return self._layer


class _Stage:
    def __init__(self, edit_target, session_layer):
        self._edit_target = edit_target
        self._session_layer = session_layer
        self.set_calls = []

    def GetEditTarget(self):
        return self._edit_target

    def SetEditTarget(self, target):
        self._edit_target = target
        self.set_calls.append(target)

    def GetSessionLayer(self):
        return self._session_layer


class _Usd:
    EditTarget = _EditTarget


def _writable_target():
    return _EditTarget(_Layer("@editable:LOP@", editable=True))


def _read_only_target():
    return _EditTarget(_Layer("@anon:0x1:LOP@", editable=False))


def _session_layer():
    return _Layer("@session@", editable=True)


def test_editable_target_is_left_untouched():
    common = _load_common()
    original = _writable_target()
    stage = _Stage(original, _session_layer())
    with common.writable_edit_target(stage, _Usd):
        assert stage.GetEditTarget() is original
    assert stage.GetEditTarget() is original
    assert stage.set_calls == []


def test_read_only_target_is_swapped_for_session_and_restored():
    common = _load_common()
    original = _read_only_target()
    session = _session_layer()
    stage = _Stage(original, session)
    with common.writable_edit_target(stage, _Usd):
        active = stage.GetEditTarget()
        assert active is not original
        assert active.GetLayer() is session
    assert stage.GetEditTarget() is original


def test_read_only_target_is_restored_even_when_the_block_raises():
    common = _load_common()
    original = _read_only_target()
    stage = _Stage(original, _session_layer())
    with pytest.raises(RuntimeError, match="boom"):
        with common.writable_edit_target(stage, _Usd):
            raise RuntimeError("boom")
    assert stage.GetEditTarget() is original


def test_invalid_current_target_falls_back_to_session():
    common = _load_common()
    invalid = _EditTarget(None)
    session = _session_layer()
    stage = _Stage(invalid, session)
    with common.writable_edit_target(stage, _Usd):
        assert stage.GetEditTarget().GetLayer() is session
    # A null target cannot be restored, so the session target stays active.
    assert stage.GetEditTarget().GetLayer() is session


def test_missing_session_layer_raises_a_clear_error():
    common = _load_common()
    stage = _Stage(_read_only_target(), session_layer=None)
    with pytest.raises(RuntimeError, match="session layer"):
        with common.writable_edit_target(stage, _Usd):
            pass


def test_unqueryable_edit_target_falls_back_to_session():
    common = _load_common()
    session = _session_layer()

    class _NoEditTarget:
        def GetEditTarget(self):
            raise RuntimeError("stage cannot report an edit target")

        def SetEditTarget(self, target):
            self.target = target

        def GetSessionLayer(self):
            return session

    stage = _NoEditTarget()
    with common.writable_edit_target(stage, _Usd):
        assert stage.GetSessionLayer() is session
    assert stage.target.GetLayer() is session


def test_editability_is_read_from_the_permissionToEdit_property():
    """OpenUSD exposes edit permission as a property; never call it as a method."""
    common = _load_common()
    assert common._layer_is_editable(_Layer("@editable@", editable=True)) is True
    assert common._layer_is_editable(_Layer("@locked@", editable=False)) is False


def test_editability_tolerates_a_callable_permission_variant():
    """A host build exposing PermissionToEdit() as a method still classifies."""
    common = _load_common()

    class _CallableLayer:
        @staticmethod
        def PermissionToEdit():
            return True

    assert common._layer_is_editable(_CallableLayer()) is True
