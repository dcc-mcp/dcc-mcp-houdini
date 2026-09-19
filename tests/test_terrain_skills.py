"""Public domain tool contracts for the heightfield terrain skill package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from domain_graph_fakes import scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-terrain"


def _load(name):
    spec = importlib.util.spec_from_file_location("terrain_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _heightfield_geometry(layers=("height", "mask")):
    box = SimpleNamespace(minvec=lambda: (0.0, 0.0, 0.0), maxvec=lambda: (1000.0, 0.0, 1000.0))

    class Geometry(SimpleNamespace):
        def numPoints(self):
            return 4

        def numPrims(self):
            return len(layers)

        def intrinsicValue(self, name):
            # Heightfields carry layer names as a prim string attribute.
            raise ValueError(name)

        def primStringAttribValues(self, name):
            if name != "name":
                raise ValueError(name)
            return list(layers)

        def boundingBox(self):
            return box

    return Geometry()


def test_create_heightfield_reports_required_setup():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_heightfield.py").create_heightfield(geo.path(), parameters={"size": 1000})
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "heightfield"
    assert context["node_path"].endswith("/heightfield1")
    assert context["setup_state"] == "skeleton"
    assert context["applied_parameters"] == {"size": 1000}
    assert any("heightfield_output" in step for step in context["required_setup"])


def test_create_heightfield_rolls_back_on_missing_parameter():
    root, geo, hou = scene()
    preserved = geo.createNode("box")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_heightfield.py").create_heightfield(geo.path(), parameters={"nope": 1})
    assert not result["success"]
    assert geo.children() == (preserved,)


def test_add_terrain_layer_wires_upstream_heightfield():
    root, geo, hou = scene()
    heightfield = geo.createNode("heightfield")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_terrain_layer.py").add_terrain_layer(geo.path(), "noise", source_path=heightfield.path())
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "heightfield_noise"
    assert context["wired"] is True
    assert context["source_path"] == heightfield.path()
    assert hou.node(context["node_path"]).inputs() == (heightfield,)


def test_add_terrain_layer_chain_reads_back_for_next_step():
    root, geo, hou = scene()
    heightfield = geo.createNode("heightfield")
    module = _load("add_terrain_layer.py")
    with patch.dict(sys.modules, {"hou": hou}):
        noise = module.add_terrain_layer(geo.path(), "noise", source_path=heightfield.path())
        erode = module.add_terrain_layer(
            geo.path(), "erode", source_path=noise["context"]["node_path"], parameters={"size": 2}
        )
        scatter = module.add_terrain_layer(geo.path(), "scatter", source_path=erode["context"]["node_path"])
    assert scatter["success"]
    node = hou.node(scatter["context"]["node_path"])
    assert node.inputs() == (hou.node(erode["context"]["node_path"]),)
    assert hou.node(erode["context"]["node_path"]).inputs() == (hou.node(noise["context"]["node_path"]),)


def test_add_terrain_layer_without_source_reports_unwired():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_terrain_layer.py").add_terrain_layer(geo.path(), "erode")
    assert result["success"]
    assert result["context"]["setup_state"] == "unwired"
    assert result["context"]["required_setup"] == ["wire the layer into the heightfield chain"]


def test_add_terrain_layer_rejects_unknown_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_terrain_layer.py").add_terrain_layer(geo.path(), "volcano")
    assert not result["success"]
    assert "Unsupported layer_type" in skill_error_detail(result)
    assert geo.children() == ()


def test_inspect_heightfield_reads_layer_names():
    root, geo, hou = scene()
    node = geo.createNode("heightfield")
    node.geometry = lambda: _heightfield_geometry()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_heightfield.py").inspect_heightfield(node.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is True
    assert context["layer_names"] == ["height", "mask"]
    assert context["layer_count"] == 2
    assert context["layer_names_available"] is True
    assert context["prim_count"] == 2
    assert context["bounding_box"] == {"min": (0.0, 0.0, 0.0), "max": (1000.0, 0.0, 1000.0)}


def test_inspect_heightfield_reports_missing_geometry_instead_of_guessing():
    root, geo, hou = scene()
    node = geo.createNode("heightfield")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_heightfield.py").inspect_heightfield(node.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is False
    assert context["layer_names"] == []
    assert context["layer_names_available"] is False
    assert context["prim_count"] is None


def test_hou_missing_returns_structured_error():
    root, geo, _hou = scene()
    assert "hou" not in sys.modules
    result = _load("add_terrain_layer.py").add_terrain_layer(geo.path(), "noise")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


def test_layer_type_map_is_stable() -> None:
    module = _load("_terrain_common.py")
    assert module.TERRAIN_LAYER_TYPES["erode"] == "heightfield_erode"
    assert module.TERRAIN_LAYER_TYPES["scatter"] == "heightfield_scatter"
    assert set(module.TERRAIN_LAYER_TYPES) == {
        "noise",
        "erode",
        "terrace",
        "distort",
        "scatter",
        "slump",
        "flowfield",
        "mask_noise",
        "copy_layer",
        "remap",
    }


def test_inspect_heightfield_distinguishes_no_layers_from_unreadable_names():
    root, geo, hou = scene()
    node = geo.createNode("heightfield")
    node.geometry = lambda: _heightfield_geometry(layers=())
    with patch.dict(sys.modules, {"hou": hou}):
        readable = _load("inspect_heightfield.py").inspect_heightfield(node.path())
    assert readable["context"]["layer_names"] == []
    assert readable["context"]["layer_names_available"] is True

    class Unreadable(SimpleNamespace):
        def numPoints(self):
            return 0

        def numPrims(self):
            return 0

        def intrinsicValue(self, name):
            raise ValueError(name)

        def primStringAttribValues(self, name):
            raise ValueError(name)

        def boundingBox(self):
            return None

    node.geometry = lambda: Unreadable()
    with patch.dict(sys.modules, {"hou": hou}):
        unreadable = _load("inspect_heightfield.py").inspect_heightfield(node.path())
    assert unreadable["context"]["layer_names"] == []
    assert unreadable["context"]["layer_names_available"] is False
