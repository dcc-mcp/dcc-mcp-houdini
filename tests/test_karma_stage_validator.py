"""Read-only Karma stage validation tests without a Houdini process."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from skill_loader import skill_script_import_context

_SCRIPT = (
    Path(__file__).parent.parent
    / "src"
    / "dcc_mcp_houdini"
    / "skills"
    / "houdini-render"
    / "scripts"
    / "validate_karma_stage.py"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("houdini_render_validate_karma_stage", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _Attribute:
    def __init__(self, value, authored: bool = True) -> None:
        self._value = value
        self._authored = authored

    def Get(self):
        return self._value

    def HasAuthoredValueOpinion(self) -> bool:
        return self._authored


class _Prim:
    def __init__(
        self,
        path: str,
        *,
        type_name: str = "Xform",
        parent=None,
        instance: bool = False,
        active: bool = True,
        attributes=None,
    ) -> None:
        self._path = path
        self._type_name = type_name
        self._parent = parent
        self._instance = instance
        self._active = active
        self._attributes = attributes or {}

    def __bool__(self) -> bool:
        return True

    def GetPath(self):
        return self._path

    def GetTypeName(self) -> str:
        return self._type_name

    def GetParent(self):
        return self._parent

    def GetAttribute(self, name: str):
        return self._attributes.get(name)

    def IsInstance(self) -> bool:
        return self._instance

    def IsActive(self) -> bool:
        return self._active


class _Stage:
    def __init__(self, prims) -> None:
        self._prims = prims

    def Traverse(self):
        return iter(self._prims)


class _Node:
    def __init__(self, stage: _Stage) -> None:
        self._stage = stage

    def path(self) -> str:
        return "/stage/OUT"

    def stage(self) -> _Stage:
        return self._stage


def _hou_module(stage: _Stage, build: int) -> ModuleType:
    module = ModuleType("hou")
    node = _Node(stage)
    module.node = lambda path: node if path == "/stage/OUT" else None  # type: ignore[attr-defined]
    module.applicationVersion = lambda: (21, 0, build)  # type: ignore[attr-defined]
    return module


def _validate(stage: _Stage, build: int = 631) -> dict:
    module = _load_script()
    with patch.dict(sys.modules, {"hou": _hou_module(stage, build)}):
        return module.validate_karma_stage("/stage/OUT")


def test_reports_prototype_only_vblur_authored_on_native_instance_ancestor() -> None:
    world = _Prim(
        "/World",
        attributes={"primvars:karma:object:vblur": _Attribute(1)},
    )
    instance = _Prim("/World/Tree_1", parent=world, instance=True)

    result = _validate(_Stage([world, instance]))

    assert result["success"] is True
    assert result["context"]["host_build"] == "21.0.631"
    diagnostic = result["context"]["diagnostics"][0]
    assert diagnostic["code"] == "KARMA_INSTANCE_VBLUR_PROTOTYPE_ONLY"
    assert diagnostic["severity"] == "warning"
    assert diagnostic["prim_path"] == "/World"
    assert diagnostic["property"] == "primvars:karma:object:vblur"
    assert "Render Geometry Settings" in diagnostic["fix_hint"]
    assert "Scene Import" in diagnostic["fix_hint"]


def test_blocked_vblur_opinion_is_not_reported() -> None:
    instance = _Prim(
        "/World/Tree_1",
        instance=True,
        attributes={"primvars:karma:object:vblur": _Attribute(None)},
    )

    result = _validate(_Stage([instance]))

    assert result["context"]["diagnostics"] == []


def test_reports_unsupported_filters_only_on_active_render_vars() -> None:
    filter_name = "driver:parameters:aov:karma:filter"
    render_vars = [
        _Prim(
            "/Render/Vars/primid",
            type_name="RenderVar",
            attributes={filter_name: _Attribute('["minmax",{"mode":"idcover"}]')},
        ),
        _Prim(
            "/Render/Vars/depth",
            type_name="RenderVar",
            attributes={filter_name: _Attribute('["minmax",{"mode":"ocover"}]')},
        ),
        _Prim(
            "/Render/Vars/element",
            type_name="RenderVar",
            attributes={filter_name: _Attribute('["minmax",{"mode":"edge"}]')},
        ),
        _Prim(
            "/Render/Vars/inactive",
            type_name="RenderVar",
            active=False,
            attributes={filter_name: _Attribute('["minmax",{"mode":"idcover"}]')},
        ),
        _Prim(
            "/Render/Vars/supported",
            type_name="RenderVar",
            attributes={filter_name: _Attribute('["ubox",{}]')},
        ),
    ]

    result = _validate(_Stage(render_vars))

    diagnostics = result["context"]["diagnostics"]
    assert [item["prim_path"] for item in diagnostics] == [
        "/Render/Vars/primid",
        "/Render/Vars/depth",
        "/Render/Vars/element",
    ]
    assert {item["code"] for item in diagnostics} == {"KARMA_UNSUPPORTED_RENDER_VAR_FILTER"}
    assert all("ray:primid" in item["fix_hint"] for item in diagnostics)
    assert all("dataType=int" in item["fix_hint"] for item in diagnostics)
    assert all("supported filter" in item["fix_hint"] for item in diagnostics)


def test_rendervisibility_is_host_known_before_21_0_762_only() -> None:
    instance = _Prim(
        "/World/Rock_1",
        instance=True,
        attributes={"primvars:karma:object:rendervisibility": _Attribute("-primary")},
    )
    stage = _Stage([instance])

    old_result = _validate(stage, build=631)
    fixed_result = _validate(stage, build=762)

    old_diagnostics = old_result["context"]["diagnostics"]
    assert [item["code"] for item in old_diagnostics] == ["KARMA_INSTANCE_RENDERVISIBILITY_HOST_DIAGNOSTIC"]
    assert old_diagnostics[0]["severity"] == "info"
    assert "21.0.762" in old_diagnostics[0]["fix_hint"]
    assert fixed_result["context"]["host_build"] == "21.0.762"
    assert fixed_result["context"]["diagnostics"] == []


def test_rejects_non_lop_nodes_and_unknown_renderers() -> None:
    module = _load_script()
    hou = _hou_module(_Stage([]), 631)
    hou.node = lambda _path: object()  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"hou": hou}):
        non_lop = module.validate_karma_stage("/obj/geo1")
        unknown_renderer = module.validate_karma_stage("/stage/OUT", renderer="mantra")

    assert non_lop["success"] is False
    assert "LOP" in non_lop["error"]
    assert unknown_renderer["success"] is False
    assert "renderer" in unknown_renderer["error"]
