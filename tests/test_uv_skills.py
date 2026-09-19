"""Public domain tool contracts for the UV skill package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from domain_graph_fakes import scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-uv"


def _load(name):
    spec = importlib.util.spec_from_file_location("uv_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _attribute(name, size):
    return SimpleNamespace(name=lambda: name, size=lambda: size)


def _uv_geometry(sets=("uv",), values=None):
    class Geometry(SimpleNamespace):
        def vertexAttribs(self):
            return [_attribute(name, 3) for name in sets]

        def pointAttribs(self):
            return [_attribute("P", 3)]

        def vertexFloatAttribValues(self, name):
            return list(values) if name == sets[0] and values is not None else []

        def pointFloatAttribValues(self, name):
            return []

    return Geometry()


def test_unwrap_uv_wires_source_and_reports_setup():
    root, geo, hou = scene()
    source = geo.createNode("box")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("unwrap_uv.py").unwrap_uv(geo.path(), "auto", source_path=source.path())
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "uvunwrap"
    assert context["wired"] is True
    assert context["setup_state"] == "wired"
    assert "pack the islands with layout_uv" in context["required_setup"]
    assert hou.node(context["node_path"]).inputs() == (source,)


def test_unwrap_uv_defaults_node_name_from_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("unwrap_uv.py").unwrap_uv(geo.path(), "atlas")
    assert result["success"]
    assert result["context"]["node_type"] == "uvlayout"
    assert result["context"]["setup_state"] == "unwired"


@pytest.mark.parametrize("script", ["unwrap_uv.py", "transform_uv.py"])
def test_uv_helpers_reject_unknown_type(script):
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = (
            _load(script).unwrap_uv(geo.path(), "nope")
            if script == "unwrap_uv.py"
            else _load(script).transform_uv(geo.path(), "nope")
        )
    assert not result["success"]
    assert "Unsupported" in skill_error_detail(result)
    assert geo.children() == ()


def test_unwrap_uv_rolls_back_on_missing_parameter():
    root, geo, hou = scene()
    source = geo.createNode("box")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("unwrap_uv.py").unwrap_uv(geo.path(), "auto", source_path=source.path(), parameters={"nope": 1})
    assert not result["success"]
    assert geo.children() == (source,)


def test_transform_uv_wires_into_the_uv_chain():
    root, geo, hou = scene()
    unwrapped = geo.createNode("uvunwrap")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("transform_uv.py").transform_uv(geo.path(), "layout", source_path=unwrapped.path())
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "uvlayout"
    assert context["wired"] is True
    assert context["required_setup"] == []
    assert hou.node(context["node_path"]).inputs() == (unwrapped,)


def test_inspect_uv_reports_sets_and_udim_tiles():
    root, geo, hou = scene()
    node = geo.createNode("uvunwrap")
    node.geometry = lambda: _uv_geometry(values=[0.2, 0.3, 1.4, 0.5, 0.1, 2.2])
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_uv.py").inspect_uv(node.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is True
    assert context["uv_sets"] == ["uv"]
    assert context["udim_detection"] == "computed"
    # 1001 + floor(u) + 10 * floor(v)
    assert context["udim_tiles"] == [1001, 1002, 1021]
    assert context["sampled_uv_set"] == "uv"


def test_inspect_uv_ignores_non_uv_attributes():
    root, geo, hou = scene()
    node = geo.createNode("uvunwrap")
    node.geometry = lambda: _uv_geometry()
    node.geometry = lambda: SimpleNamespace(
        vertexAttribs=lambda: [_attribute("P", 3), _attribute("N", 3)],
        pointAttribs=list,
    )
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_uv.py").inspect_uv(node.path())
    assert result["context"]["uv_sets"] == []
    assert result["context"]["udim_detection"] == "no_uv_sets"
    assert result["context"]["udim_tiles"] == []


def test_inspect_uv_reports_unreadable_values():
    root, geo, hou = scene()
    node = geo.createNode("uvunwrap")

    class Geometry(SimpleNamespace):
        def vertexAttribs(self):
            return [_attribute("uv", 3)]

        def pointAttribs(self):
            return []

    node.geometry = lambda: Geometry()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_uv.py").inspect_uv(node.path())
    assert result["context"]["uv_sets"] == ["uv"]
    assert result["context"]["udim_detection"] == "no_values"


def test_inspect_uv_reports_missing_geometry_instead_of_guessing():
    root, geo, hou = scene()
    node = geo.createNode("uvunwrap")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_uv.py").inspect_uv(node.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is False
    assert context["uv_sets"] == []
    assert context["udim_detection"] == "unavailable"


# `inspect_uv` shares the guarded `cooked_geometry` helper, whose no-implicit-cook
# behaviour is asserted for the vdb and terrain packages in the PR that lands it.


def test_inspect_uv_bounds_max_sets():
    root, geo, hou = scene()
    node = geo.createNode("uvunwrap")
    with patch.dict(sys.modules, {"hou": hou}):
        bounded = _load("inspect_uv.py").inspect_uv(node.path(), max_sets=99)
        ok = _load("inspect_uv.py").inspect_uv(node.path(), max_sets=1)
    assert not bounded["success"]
    assert ok["success"]


def test_hou_missing_returns_structured_error():
    root, geo, _hou = scene()
    assert "hou" not in sys.modules
    result = _load("unwrap_uv.py").unwrap_uv(geo.path(), "auto")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


def test_uv_payloads_do_not_advertise_skipped_parameters():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        unwrapped = _load("unwrap_uv.py").unwrap_uv(geo.path(), "auto")
        transformed = _load("transform_uv.py").transform_uv(geo.path(), "fuse")
    for result in (unwrapped, transformed):
        assert result["success"]
        assert "skipped_parameters" not in result["context"]
