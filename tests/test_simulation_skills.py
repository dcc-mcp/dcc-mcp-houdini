"""Public domain tool contracts with explicit HOM doubles."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from domain_graph_fakes import Parm, scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-simulation"


def _load(name):
    spec = importlib.util.spec_from_file_location("simulation_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("family", ["pyro", "flip", "rbd", "vellum"])
def test_create_simulation_network_is_explicit_skeleton(family):
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_simulation_network.py").create_simulation_network(
            root.path(), family, parameters={"timescale": 0.5}
        )
    assert result["success"]
    assert result["context"]["setup_state"] == "skeleton"
    assert result["context"]["simulation_verified"] is False
    assert result["context"]["applied_parameters"] == {"timescale": 0.5}
    assert hou.node(result["context"]["solver_path"]).type().name() == family + "solver"


def test_failed_creation_preserves_existing_network():
    root, geo, hou = scene()
    network = root.createNode("dopnet")
    preserved = network.createNode("null")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_simulation_network.py").create_simulation_network(
            root.path(), "pyro", parameters={"missing": 1}
        )
    assert not result["success"]
    assert network.children() == (preserved,) and not network.destroyed


def test_failed_creation_cleans_new_network():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_simulation_network.py").create_simulation_network(
            root.path(), "pyro", parameters={"missing": 1}
        )
    assert not result["success"]
    assert root.node("dopnet1") is None


def test_configuration_rolls_back_parameters_on_cook_failure():
    root, geo, hou = scene()
    solver = root.createNode("dopnet").createNode("pyrosolver")
    solver.parm("timescale").keys = ("animated expression",)
    solver.error_messages = ["bad source"]
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_simulation_solver.py").configure_simulation_solver(
            solver.path(), {"timescale": 0.5}, cook=True
        )
    assert not result["success"]
    assert solver.parm("timescale").keys == ("animated expression",)


def test_validation_rejects_disconnected_solver_and_child_errors():
    root, geo, hou = scene()
    network = root.createNode("dopnet")
    solver = network.createNode("flipsolver")
    solver._type = "flipsolver::2.0"
    mod = _load("validate_simulation_setup.py")
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.validate_simulation_setup(network.path(), "flip")
        assert not result["context"]["valid"]
        source = network.createNode("flipobject")
        solver.setInput(0, source)
        source.error_messages = ["missing particles"]
        assert not mod.validate_simulation_setup(network.path(), "flip")["context"]["valid"]
        source.error_messages = []
        result = mod.validate_simulation_setup(network.path(), "flip")
        assert result["context"]["valid"] and not result["context"]["simulation_verified"]


def test_configuration_preflights_all_parameter_names():
    root, geo, hou = scene()
    solver = root.createNode("dopnet").createNode("rbdsolver")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_simulation_solver.py").configure_simulation_solver(
            solver.path(), {"timescale": 0.5, "bad-name": 1}
        )
    assert not result["success"]
    assert solver.parm("timescale").eval() == 1


def test_create_fracture_wires_source_and_reports_skipped_parameters():
    root, geo, hou = scene()
    source = geo.createNode("box")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_fracture.py").create_fracture(
            geo.path(), "voronoi", source_path=source.path(), parameters={"missing": 4}
        )
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "voronoifracture"
    assert context["wired"] is True
    assert context["source_path"] == source.path()
    assert context["skipped_parameters"] == ["missing"]
    assert hou.node(context["node_path"]).inputs() == (source,)


def test_create_fracture_rejects_unknown_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_fracture.py").create_fracture(geo.path(), "shatter")
    assert not result["success"]
    assert "Unsupported fracture_type" in skill_error_detail(result)
    assert geo.children() == ()


def test_create_fracture_requires_sop_parent():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_fracture.py").create_fracture(root.path(), "voronoi")
    assert not result["success"]
    assert "Sop" in skill_error_detail(result)


def test_create_constraint_network_creates_relationship_and_sets_sop_path():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    network = _load("create_constraint_network.py")
    with patch.dict(sys.modules, {"hou": hou}):
        result = network.create_constraint_network(dopnet.path(), "glue", relationship_parent=geo.path())
    assert result["success"]
    context = result["context"]
    assert context["relationship_path"].endswith("/glueconrel")
    # The fake exposes no soppath parameter, so the override is reported, not applied.
    assert context["skipped_parameters"] == ["soppath"]
    assert context["simulation_verified"] is False
    assert dopnet.node("constraintnetwork1") is not None


def test_create_constraint_network_applies_sop_path_when_exposed():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    mod = _load("create_constraint_network.py")
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.create_constraint_network(dopnet.path(), "wire", relationship_parent=geo.path())
    assert result["success"]
    assert result["context"]["skipped_parameters"] == ["soppath"]
    network = hou.node(result["context"]["network_path"])
    network.parms["soppath"] = Parm("soppath", "")
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.create_constraint_network(dopnet.path(), "wire", relationship_parent=geo.path())
    assert result["success"]
    assert result["context"]["created_network"] is False
    assert result["context"]["applied_parameters"]["soppath"].endswith("/wireconrel")
    assert result["context"]["skipped_parameters"] == []


def test_create_constraint_network_rejects_unknown_type():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_constraint_network.py").create_constraint_network(dopnet.path(), "rope")
    assert not result["success"]
    assert "Unsupported constraint_type" in skill_error_detail(result)
    assert dopnet.children() == ()


def test_create_collision_source_attaches_to_solver():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    solver = dopnet.createNode("rbdsolver")
    ground = geo.createNode("grid")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_collision_source.py").create_collision_source(dopnet.path(), ground.path())
    assert result["success"]
    context = result["context"]
    assert context["collision_type"] == "static"
    assert context["source_path"] == ground.path()
    assert context["attached_to"] == solver.path()
    assert context["attached_input_index"] == 0
    assert context["skipped_parameters"] == ["soppath"]
    assert context["simulation_verified"] is False
    assert solver.inputs() == (hou.node(context["node_path"]),)


def test_create_collision_source_rejects_foreign_connect_to():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    dopnet.createNode("rbdsolver")
    stray = geo.createNode("null")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_collision_source.py").create_collision_source(
            dopnet.path(), geo.path(), connect_to=stray.path()
        )
    assert not result["success"]
    assert "connect_to must name a node inside" in skill_error_detail(result)
    assert stray.parent() is geo


def test_apply_parameters_reports_missing_names_and_rolls_back():
    root, geo, hou = scene()
    node = root.createNode("dopnet")
    node.parms["soppath"] = Parm("soppath", "")
    common = _load("_simulation_common.py")
    with common.apply_parameters(node, {"soppath": "/obj/geo1/grid1", "missing": 1}) as (applied, skipped):
        assert applied == {"soppath": "/obj/geo1/grid1"}
        assert skipped == ["missing"]
        assert node.parm("soppath").eval() == "/obj/geo1/grid1"
    node.parms["size"] = Parm("size", 1)
    with pytest.raises(RuntimeError):
        with common.apply_parameters(node, {"size": 9}):
            raise RuntimeError("boom")
    assert node.parm("size").eval() == 1
