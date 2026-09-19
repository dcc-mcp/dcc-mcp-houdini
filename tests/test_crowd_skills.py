"""Public domain tool contracts for the crowd skill package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from domain_graph_fakes import scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-crowds"


def _load(name):
    spec = importlib.util.spec_from_file_location("crowd_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_create_crowd_network_is_explicit_skeleton():
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_crowd_network.py").create_crowd_network(root.path(), parameters={"timescale": 0.5})
    assert result["success"]
    context = result["context"]
    assert context["setup_state"] == "skeleton"
    assert context["simulation_verified"] is False
    assert context["applied_parameters"] == {"timescale": 0.5}
    assert context["solver_path"].endswith("/crowdsolver1")
    assert context["object_path"].endswith("/crowdobject1")
    solver = hou.node(context["solver_path"])
    assert [c.inputItem().path() for c in solver.inputConnections()] == [context["object_path"]]


def test_create_crowd_network_has_no_dead_skipped_parameters():
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_crowd_network.py").create_crowd_network(root.path())
    assert result["success"]
    assert "skipped_parameters" not in result["context"]


def test_create_crowd_network_reuses_existing_network():
    root, _geo, hou = scene()
    network = root.createNode("dopnet", "crowdsim1")
    solver = network.createNode("crowdsolver", "crowdsolver1")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_crowd_network.py").create_crowd_network(root.path(), parameters={"timescale": 2})
    assert result["success"]
    assert result["context"]["created_network"] is False
    assert solver.parm("timescale").eval() == 2


def test_create_crowd_network_cleans_up_on_missing_parameter():
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_crowd_network.py").create_crowd_network(root.path(), parameters={"missing": 1})
    assert not result["success"]
    assert root.node("crowdsim1") is None


def test_add_crowd_behavior_attaches_to_solver():
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    solver = network.createNode("crowdsolver")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_crowd_behavior.py").add_crowd_behavior(network.path(), "steer")
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "crowd_steer"
    assert context["attached_to"] == solver.path()
    assert context["attached_input_index"] == 0
    assert solver.inputs() == (hou.node(context["node_path"]),)


def test_add_crowd_behavior_honours_explicit_connect_to():
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    network.createNode("crowdsolver")
    other = network.createNode("crowd_avoid")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_crowd_behavior.py").add_crowd_behavior(network.path(), "seek", connect_to=other.path())
    assert result["success"]
    assert result["context"]["node_type"] == "crowd_seek"
    assert result["context"]["attached_to"] == other.path()


def test_add_crowd_behavior_unattached_without_solver():
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_crowd_behavior.py").add_crowd_behavior(network.path(), "avoid")
    assert result["success"]
    assert result["context"]["setup_state"] == "unattached"
    assert result["context"]["required_setup"] == ["connect the behavior into the solver chain"]


def test_add_crowd_behavior_rejects_foreign_target():
    root, geo, hou = scene()
    network = root.createNode("dopnet")
    network.createNode("crowdsolver")
    stray = geo.createNode("null")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_crowd_behavior.py").add_crowd_behavior(network.path(), "steer", connect_to=stray.path())
    assert not result["success"]
    assert "connect_to must name a node inside" in skill_error_detail(result)


@pytest.mark.parametrize("step", ["nope", "", "steering"])
def test_add_crowd_behavior_rejects_unknown_type(step):
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    network.createNode("crowdsolver")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_crowd_behavior.py").add_crowd_behavior(network.path(), step)
    assert not result["success"]
    assert "Unsupported behavior_type" in skill_error_detail(result)
    assert len(network.children()) == 1


def test_inspect_crowd_reports_structure_only():
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    network.createNode("crowdsolver")
    network.createNode("crowdobject")
    network.createNode("crowd_steer")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_crowd.py").inspect_crowd(network.path())
    assert result["success"]
    context = result["context"]
    assert context["node_count"] == 3
    assert context["has_solver"] is True
    assert context["has_agents"] is True
    assert context["behavior_count"] == 1
    assert context["validation_scope"] == "graph_structure"
    assert context["simulation_verified"] is False


def test_inspect_crowd_caps_node_count():
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    for index in range(3):
        network.createNode("crowd_steer", "steer{}".format(index))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_crowd.py").inspect_crowd(network.path(), max_nodes=2)
    assert result["context"]["node_count"] == 2
    assert result["context"]["truncated"] is True


@pytest.mark.parametrize("max_nodes", [0, "2", None])
def test_inspect_crowd_validates_max_nodes(max_nodes):
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_crowd.py").inspect_crowd(network.path(), max_nodes=max_nodes)
    assert not result["success"]


def test_hou_missing_returns_structured_error():
    root, _geo, _hou = scene()
    assert "hou" not in sys.modules
    result = _load("add_crowd_behavior.py").add_crowd_behavior("/obj/crowdsim1", "steer")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


def test_crowd_package_registers_expected_tools() -> None:
    import yaml

    tools = yaml.safe_load((_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    assert [tool["name"] for tool in tools] == [
        "create_crowd_network",
        "add_crowd_behavior",
        "inspect_crowd",
    ]
    for tool in tools:
        assert tool["input_schema"]["additionalProperties"] is False


def test_reused_solver_is_not_rewired_when_parameters_fail():
    """A reused solver is not owned, so a failed call must not change its wiring."""
    root, _geo, hou = scene()
    network = root.createNode("dopnet", "crowdsim1")
    solver = network.createNode("crowdsolver", "crowdsolver1")
    upstream = network.createNode("crowdobject", "existing_agents")
    solver.setInput(0, upstream)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_crowd_network.py").create_crowd_network(root.path(), parameters={"missing": 1})
    assert not result["success"]
    # The pre-existing connection must be untouched.
    assert solver.inputs() == (upstream,)


def test_reused_solver_is_rewired_on_success():
    root, _geo, hou = scene()
    network = root.createNode("dopnet", "crowdsim1")
    solver = network.createNode("crowdsolver", "crowdsolver1")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_crowd_network.py").create_crowd_network(root.path())
    assert result["success"]
    crowd_object = hou.node(result["context"]["object_path"])
    assert solver.inputs() == (crowd_object,)


def test_solver_lookup_ignores_versioned_node_types():
    """Houdini reports crowdsolver::2.0; the version suffix must not hide it."""
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    solver = network.createNode("crowdsolver::2.0")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_crowd_behavior.py").add_crowd_behavior(network.path(), "steer")
    assert result["success"]
    assert result["context"]["attached_to"] == solver.path()


def test_inspect_crowd_normalises_versioned_types():
    root, _geo, hou = scene()
    network = root.createNode("dopnet")
    network.createNode("crowdsolver::2.0")
    network.createNode("crowdobject::2.0")
    network.createNode("crowd_steer::2.0")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_crowd.py").inspect_crowd(network.path())
    context = result["context"]
    assert context["has_solver"] is True
    assert context["has_agents"] is True
    assert context["behavior_count"] == 1
