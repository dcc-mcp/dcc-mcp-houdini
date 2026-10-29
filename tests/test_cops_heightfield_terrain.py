"""Regression contracts for the COPS heightfield terrain authoring flow.

"COPS heightfields" terrain = a Copernicus network that turns procedural noise
into a heightfield volume (``fractalnoise -> mono -> monotoheightfield``), shapes
it with Copernicus heightfield operators (``heightfield_erode`` /
``heightfield_terrace``), and ends in an image ROP. On a real Houdini host this
chain cooks to non-flat heightfield voxels (see
``docs/guide/cops-heightfield-terrain-test.md``). These tests use the shared HOM
doubles to lock in the adapter's tool contracts without a live host, so the
terrain recipe stays verifiable in CI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from domain_graph_fakes import scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_SKILLS = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills"
_ROOTS = {
    "cop": _SKILLS / "houdini-copernicus" / "scripts",
    "terrain": _SKILLS / "houdini-terrain" / "scripts",
}

# The proven real-host recipe, expressed as build_composite_chain steps.
TERRAIN_CHAIN = [
    {"filter_type": "fractalnoise", "node_name": "noise_src"},
    {"filter_type": "mono", "node_name": "to_mono"},
    {"filter_type": "monotoheightfield", "node_name": "to_heightfield"},
    {"filter_type": "heightfield_erode", "node_name": "hf_erode"},
    {"filter_type": "heightfield_terrace", "node_name": "hf_terrace"},
    {"filter_type": "output", "node_name": "hf_out"},
]
TERRAIN_NODE_TYPES = [
    "fractalnoise",
    "mono",
    "monotoheightfield",
    "heightfield_erode",
    "heightfield_terrace",
    "rop_image",
]


def _load(kind, name):
    spec = importlib.util.spec_from_file_location("{}_{}".format(kind, name[:-3]), _ROOTS[kind] / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _heightfield_geometry():
    box = SimpleNamespace(
        minvec=lambda: (-1.0, -1.0, 0.18),
        maxvec=lambda: (1.0, 1.0, 0.83),
    )

    class Geometry(SimpleNamespace):
        def numPoints(self):
            return 4

        def numPrims(self):
            return 1

        def intrinsicValue(self, name):
            raise ValueError(name)

        def primStringAttribValues(self, name):
            if name != "name":
                raise ValueError(name)
            return ["height"]

        def boundingBox(self):
            return box

    return Geometry()


def _build_network(hou, geo_path):
    """Create a Cop network and the full COPS heightfield terrain chain."""
    network = _load("cop", "create_cop_network.py").create_cop_network(geo_path, network_name="copnet_terrain")
    return network["context"]["network_path"]


def test_cops_heightfield_terrain_chain_authors_and_wires():
    """The whole noise->mono->heightfield->erode->terrace->output recipe builds."""
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        network_path = _build_network(hou, geo.path())
        result = _load("cop", "build_composite_chain.py").build_composite_chain(network_path, steps=TERRAIN_CHAIN)
    assert result["success"]
    context = result["context"]
    assert context["node_count"] == len(TERRAIN_CHAIN)
    assert [item["node_type"] for item in context["nodes"]] == TERRAIN_NODE_TYPES
    # Every step after the noise source is wired into the previous one.
    assert all(item["wired"] for item in context["nodes"][1:])
    assert context["first_node_path"].endswith("/noise_src")
    assert context["last_node_path"].endswith("/hf_out")


def test_cops_heightfield_terrain_chain_cooks_clean():
    """Cooking the heightfield node reports an honest, valid result."""
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        network_path = _build_network(hou, geo.path())
        chain = _load("cop", "build_composite_chain.py").build_composite_chain(network_path, steps=TERRAIN_CHAIN)
        hf_path = chain["context"]["nodes"][2]["node_path"]
        cook = _load("cop", "cook_cop_node.py").cook_cop_node(hf_path)
    assert cook["success"]
    assert cook["context"]["cooked"] is True
    assert cook["context"]["valid"] is True
    assert cook["context"]["artifact_verified"] is False  # cook never claims a PNG


def test_cops_heightfield_terrain_network_validates_after_authoring():
    """A freshly authored terrain network has no cached cook errors."""
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        network_path = _build_network(hou, geo.path())
        _load("cop", "build_composite_chain.py").build_composite_chain(network_path, steps=TERRAIN_CHAIN)
        validation = _load("cop", "validate_cop_network.py").validate_cop_network(network_path)
    assert validation["success"]
    assert validation["context"]["valid"] is True
    assert validation["context"]["node_count"] == len(TERRAIN_CHAIN)
    assert validation["context"]["errors"] == []


def test_cops_heightfield_terrain_inspection_reads_graph():
    """Read-only inspection reports every node and its input wiring."""
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        network_path = _build_network(hou, geo.path())
        _load("cop", "build_composite_chain.py").build_composite_chain(network_path, steps=TERRAIN_CHAIN)
        inspection = _load("cop", "inspect_cop_network.py").inspect_cop_network(network_path)
    assert inspection["success"]
    context = inspection["context"]
    assert context["node_count"] == len(TERRAIN_CHAIN)
    wired = [node for node in context["nodes"] if node["inputs"]]
    # Five of six nodes have an upstream input; the noise source has none.
    assert len(wired) == len(TERRAIN_CHAIN) - 1


def test_cops_heightfield_terrain_artifact_is_verified(tmp_path):
    """inspect_cop_output confirms a rendered heightmap actually exists on disk."""
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        network_path = _build_network(hou, geo.path())
        chain = _load("cop", "build_composite_chain.py").build_composite_chain(network_path, steps=TERRAIN_CHAIN)
        rop_path = chain["context"]["last_node_path"]
        artifact = tmp_path / "cops_heightfield_terrain_height.png"
        artifact.write_bytes(b"PNGDATA" * 64)
        inspection = _load("cop", "inspect_cop_output.py").inspect_cop_output(rop_path, output_path=str(artifact))
    assert inspection["success"]
    context = inspection["context"]
    assert context["artifact_exists"] is True
    assert context["artifact_size_bytes"] == artifact.stat().st_size
    assert context["render_verified"] is False  # stat, not a render claim


def test_cops_heightfield_terrain_heightfield_readback():
    """The terrain skill reads a cooked heightfield's layer and bounds."""
    root, geo, hou = scene()
    node = geo.createNode("heightfield")
    node.geometry = lambda: _heightfield_geometry()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("terrain", "inspect_heightfield.py").inspect_heightfield(node.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is True
    assert context["layer_names"] == ["height"]
    assert context["bounding_box"] == {"min": (-1.0, -1.0, 0.18), "max": (1.0, 1.0, 0.83)}


def test_cops_heightfield_terrain_chain_rolls_back_on_bad_parameter():
    """A bad parameter in one step destroys every node the chain created."""
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        network_path = _build_network(hou, geo.path())
        steps = list(TERRAIN_CHAIN)
        steps[3] = {"filter_type": "heightfield_erode", "parameters": {"nope": 1}}
        result = _load("cop", "build_composite_chain.py").build_composite_chain(network_path, steps=steps)
    assert not result["success"]
    # Require the bad parameter name in the error detail so an unrelated
    # failure (e.g. a missing network) cannot satisfy this check.
    assert "nope" in skill_error_detail(result)
    assert hou.node(network_path).children() == ()


def test_cops_heightfield_terrain_rejects_legacy_cop2_network():
    """A pre-existing COP2 network is refused, not silently reused."""
    from domain_graph_fakes import Node

    root, geo, hou = scene()
    Node(geo.path() + "/copnet_terrain", "cop2net", geo, "Cop2")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("cop", "create_cop_network.py").create_cop_network(geo.path(), network_name="copnet_terrain")
    assert not result["success"]
