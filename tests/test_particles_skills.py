"""Public domain tool contracts for the POP particle skill package."""

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

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-particles"


def _load(name):
    spec = importlib.util.spec_from_file_location("particles_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _pop_network(root, name="popnet1"):
    network = root.createNode("popnet", name)
    solver = network.createNode("popsolver")
    return network, solver


def test_create_pop_network_is_explicit_skeleton():
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pop_network.py").create_pop_network(root.path(), parameters={"timescale": 0.5})
    assert result["success"]
    context = result["context"]
    assert context["setup_state"] == "skeleton"
    assert context["simulation_verified"] is False
    assert context["applied_parameters"] == {"timescale": 0.5}
    assert context["solver_path"].endswith("/popsolver1")
    assert context["source_path"].endswith("/popsource1")
    # DOP solvers take their simulated objects on input 0.
    solver = hou.node(context["solver_path"])
    assert [connection.inputItem().path() for connection in solver.inputConnections()] == [context["object_path"]]
    assert [connection.inputIndex() for connection in solver.inputConnections()] == [0]


def test_create_pop_network_reuses_existing_network():
    root, _geo, hou = scene()
    network, solver = _pop_network(root)
    preserved = network.createNode("null")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pop_network.py").create_pop_network(root.path(), parameters={"timescale": 2})
    assert result["success"]
    assert result["context"]["created_network"] is False
    assert result["context"]["network_path"] == network.path()
    assert solver.parm("timescale").eval() == 2
    assert preserved.parent() is network


def test_failed_creation_cleans_new_network():
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pop_network.py").create_pop_network(root.path(), parameters={"missing": 1})
    assert not result["success"]
    assert "missing" in skill_error_detail(result)
    assert root.node("popnet1") is None


def test_failed_creation_preserves_existing_network():
    root, _geo, hou = scene()
    network, _solver = _pop_network(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pop_network.py").create_pop_network(root.path(), parameters={"missing": 1})
    assert not result["success"]
    assert network.node("popsolver1") is not None and not network.destroyed


def test_add_particle_force_attaches_to_next_free_solver_input():
    root, _geo, hou = scene()
    network, solver = _pop_network(root)
    solver.setInput(0, network.createNode("popobject"))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_particle_force.py").add_particle_force(network.path(), "wind")
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "popwind"
    assert context["attached_to"] == solver.path()
    assert context["attached_input_index"] == 1
    assert [connection.inputItem().path() for connection in solver.inputConnections()][1] == context["node_path"]


def test_add_particle_behavior_honours_explicit_connect_to():
    root, _geo, hou = scene()
    network, solver = _pop_network(root)
    other = network.createNode("popforce")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_particle_behavior.py").add_particle_behavior(
            network.path(), "kill", connect_to=other.path()
        )
    assert result["success"]
    assert result["context"]["node_type"] == "popkill"
    assert result["context"]["attached_to"] == other.path()
    assert other.inputs() == (hou.node(result["context"]["node_path"]),)


def test_unattached_pop_node_reports_required_setup():
    root, _geo, hou = scene()
    network = root.createNode("popnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_particle_force.py").add_particle_force(network.path(), "drag")
    assert result["success"]
    assert result["context"]["setup_state"] == "unattached"
    assert result["context"]["attached_to"] is None
    assert result["context"]["required_setup"] == ["connect the POP node into the solver chain"]


@pytest.mark.parametrize(
    "script,kwargs",
    [
        ("add_particle_force.py", {"force_type": "nope"}),
        ("add_particle_behavior.py", {"behavior_type": "nope"}),
    ],
)
def test_pop_helpers_reject_unknown_type(script, kwargs):
    root, _geo, hou = scene()
    network, _solver = _pop_network(root)
    module = _load(script)
    caller = module.add_particle_force if "force_type" in kwargs else module.add_particle_behavior
    with patch.dict(sys.modules, {"hou": hou}):
        result = caller(network.path(), "nope")
    assert not result["success"]
    assert "Unsupported" in skill_error_detail(result)
    assert network.children() == (_solver,)


def test_configure_pop_source_rolls_back_parameters_on_cook_failure():
    root, _geo, hou = scene()
    network, solver = _pop_network(root)
    source = network.createNode("popsource")
    source.parm("timescale").keys = ("animated expression",)
    source.error_messages = ["bad source"]
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_pop_source.py").configure_pop_source(source.path(), {"timescale": 0.5}, cook=True)
    assert not result["success"]
    assert source.parm("timescale").keys == ("animated expression",)
    assert solver.parm("timescale").eval() == 1


def test_configure_pop_source_preflights_all_parameter_names():
    root, _geo, hou = scene()
    network, _solver = _pop_network(root)
    source = network.createNode("popsource")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_pop_source.py").configure_pop_source(source.path(), {"bad-name": 1})
    assert not result["success"]
    assert source.parm("timescale").eval() == 1


def test_inspect_particles_reports_missing_geometry_instead_of_guessing():
    root, _geo, hou = scene()
    network, _solver = _pop_network(root)
    pop_object = network.createNode("popobject")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_particles.py").inspect_particles(pop_object.path())
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is False
    assert context["particle_count"] is None
    assert context["attributes"] == []
    assert context["simulation_verified"] is False


def test_inspect_particles_reads_counts_and_attributes():
    root, _geo, hou = scene()
    network, _solver = _pop_network(root)
    pop_object = network.createNode("popobject")
    velocity = SimpleNamespace(name=lambda: "v", size=lambda: 3, dataType=lambda: SimpleNamespace(name=lambda: "float"))
    lifetime = SimpleNamespace(
        name=lambda: "life", size=lambda: 1, dataType=lambda: SimpleNamespace(name=lambda: "float")
    )
    box = SimpleNamespace(minvec=lambda: (0.0, 1.0, 2.0), maxvec=lambda: (3.0, 4.0, 5.0))
    pop_object.geometry = lambda: SimpleNamespace(
        points=lambda: [object(), object(), object()],
        pointAttribs=lambda: [velocity, lifetime],
        boundingBox=lambda: box,
    )
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_particles.py").inspect_particles(pop_object.path(), attributes=["v"])
    assert result["success"]
    context = result["context"]
    assert context["geometry_available"] is True
    assert context["particle_count"] == 3
    assert context["attributes"] == [{"name": "v", "size": 3, "type": "float"}]
    assert context["bounding_box"] == {"min": (0.0, 1.0, 2.0), "max": (3.0, 4.0, 5.0)}
    assert context["truncated_attributes"] is False


def test_inspect_particles_bounds_attribute_names():
    root, _geo, hou = scene()
    network, _solver = _pop_network(root)
    pop_object = network.createNode("popobject")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_particles.py").inspect_particles(pop_object.path(), attributes=["bad name"])
    assert not result["success"]
    assert "Invalid attribute name" in skill_error_detail(result)


def test_hou_missing_returns_structured_error():
    root, _geo, _hou = scene()
    network = root.createNode("popnet")
    assert "hou" not in sys.modules
    result = _load("add_particle_force.py").add_particle_force(network.path(), "wind")
    assert not result["success"]
    assert result["message"] == "Houdini not available"
    assert "hou could not be imported" in skill_error_detail(result)


def test_skill_package_registers_expected_tools() -> None:
    import yaml

    tools = yaml.safe_load((_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    assert [tool["name"] for tool in tools] == [
        "create_pop_network",
        "configure_pop_source",
        "add_particle_force",
        "add_particle_behavior",
        "inspect_particles",
    ]
    for tool in tools:
        assert tool["input_schema"]["additionalProperties"] is False


def test_pop_type_maps_and_base_type() -> None:
    module = _load("_particles_common.py")
    assert set(module.FORCE_TYPES) == {"force", "wind", "drag", "vortex", "attract", "axis"}
    assert set(module.BEHAVIOR_TYPES) == {"kill", "replicate", "split", "limit", "collide", "steer"}
    assert module.base_type("popsolver::3.0") == "popsolver"
    assert module.base_type("popwind") == "popwind"
