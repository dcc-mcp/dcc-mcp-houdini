"""Public domain tool contracts for the VDB volume skill package."""

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

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-vdb"


def _load(name):
    spec = importlib.util.spec_from_file_location("vdb_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _volume_geometry(grid_names=("density", "temperature"), prims=2, points=8):
    box = SimpleNamespace(minvec=lambda: (-1.0, -1.0, -1.0), maxvec=lambda: (1.0, 1.0, 1.0))

    def intrinsic(name):
        if name != "vdb_grids":
            raise ValueError(name)
        return " ".join(grid_names)

    return SimpleNamespace(
        numPoints=lambda: points,
        numPrims=lambda: prims,
        intrinsicValue=intrinsic,
        boundingBox=lambda: box,
    )


def test_create_vdb_node_wires_source():
    root, geo, hou = scene()
    source = geo.createNode("box")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_vdb_node.py").create_vdb_node(
            geo.path(), "from_polygons", source_path=source.path(), parameters={"size": 2}
        )
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "vdbfrompolygons"
    assert context["vdb_type"] == "from_polygons"
    assert context["source_paths"] == [source.path()]
    assert context["wired_inputs"] == [0]
    assert context["applied_parameters"] == {"size": 2}
    assert hou.node(context["node_path"]).inputs() == (source,)


def test_create_vdb_node_defaults_node_name_from_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_vdb_node.py").create_vdb_node(geo.path(), "resample")
    assert result["success"]
    assert result["context"]["node_path"].endswith("/vdbresample1")
    assert result["context"]["setup_state"] == "unwired"


def test_create_vdb_node_rejects_second_input_for_single_input_types():
    root, geo, hou = scene()
    source = geo.createNode("box")
    other = geo.createNode("sphere")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_vdb_node.py").create_vdb_node(
            geo.path(), "smooth", source_path=source.path(), source_b_path=other.path()
        )
    assert not result["success"]
    assert "source_b_path is only supported" in skill_error_detail(result)
    assert geo.children() == (source, other)


def test_create_vdb_node_wires_two_inputs_for_combine():
    root, geo, hou = scene()
    first = geo.createNode("box")
    second = geo.createNode("sphere")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_vdb_node.py").create_vdb_node(
            geo.path(), "combine", source_path=first.path(), source_b_path=second.path()
        )
    assert result["success"]
    assert result["context"]["wired_inputs"] == [0, 1]
    assert hou.node(result["context"]["node_path"]).inputs() == (first, second)


def test_create_vdb_node_rejects_unknown_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_vdb_node.py").create_vdb_node(geo.path(), "vdbify")
    assert not result["success"]
    assert "Unsupported vdb_type" in skill_error_detail(result)
    assert geo.children() == ()


def test_create_vdb_node_rolls_back_on_missing_parameter():
    root, geo, hou = scene()
    source = geo.createNode("box")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_vdb_node.py").create_vdb_node(
            geo.path(), "smooth", source_path=source.path(), parameters={"nope": 1}
        )
    assert not result["success"]
    assert "nope" in skill_error_detail(result)
    assert geo.children() == (source,)


def test_combine_vdbs_requires_same_network():
    root, geo, hou = scene()
    other = root.createNode("geo")
    stray = other.createNode("box", "stray")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("combine_vdbs.py").combine_vdbs(geo.path(), stray.path(), stray.path())
    assert not result["success"]
    assert "both sources must be nodes in" in skill_error_detail(result)
    assert geo.children() == ()


def test_combine_vdbs_wires_both_inputs():
    root, geo, hou = scene()
    first = geo.createNode("box")
    second = geo.createNode("sphere")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("combine_vdbs.py").combine_vdbs(geo.path(), first.path(), second.path())
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "vdbcombine"
    assert context["source_paths"] == [first.path(), second.path()]
    assert context["wired_inputs"] == [0, 1]
    assert hou.node(context["node_path"]).inputs() == (first, second)


def test_inspect_vdb_reads_grid_names_and_bounds():
    root, geo, hou = scene()
    node = geo.createNode("vdbfrompolygons")
    node.geometry = lambda: _volume_geometry()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_vdb.py").inspect_vdb(node.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is True
    assert context["volume_names"] == ["density", "temperature"]
    assert context["volume_count"] == 2
    assert context["prim_count"] == 2
    assert context["point_count"] == 8
    assert context["bounding_box"] == {"min": (-1.0, -1.0, -1.0), "max": (1.0, 1.0, 1.0)}


def test_inspect_vdb_reports_missing_geometry_instead_of_guessing():
    root, geo, hou = scene()
    node = geo.createNode("vdbfrompolygons")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_vdb.py").inspect_vdb(node.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is False
    assert context["volume_names"] == []
    assert context["prim_count"] is None
    assert context["bounding_box"] is None


def test_inspect_vdb_bounds_max_names():
    root, geo, hou = scene()
    node = geo.createNode("vdbfrompolygons")
    node.geometry = lambda: _volume_geometry(grid_names=("a", "b", "c"))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_vdb.py").inspect_vdb(node.path(), max_names=2)
    assert result["context"]["volume_names"] == ["a", "b"]
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_vdb.py").inspect_vdb(node.path(), max_names=99)
    assert not result["success"]


def test_hou_missing_returns_structured_error():
    root, geo, _hou = scene()
    assert "hou" not in sys.modules
    result = _load("create_vdb_node.py").create_vdb_node(geo.path(), "smooth")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


@pytest.mark.parametrize("tool", ["create_vdb_node", "combine_vdbs", "inspect_vdb"])
def test_tools_declare_strict_input_schema(tool) -> None:
    import yaml

    tools = yaml.safe_load((_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    entry = next(item for item in tools if item["name"] == tool)
    assert entry["input_schema"]["additionalProperties"] is False
    assert entry["source_file"] == "scripts/{}.py".format(tool)
