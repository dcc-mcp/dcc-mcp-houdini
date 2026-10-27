"""Public domain tool contracts with explicit HOM doubles."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
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


@pytest.mark.parametrize(
    ("constraint_type", "node_type"),
    [("glue", "glueconrel"), ("soft", "bulletsoftconrel"), ("cone", "conetwistconrel")],
)
def test_create_constraint_network_wires_relationship_in_same_dop_network(constraint_type, node_type):
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    network = _load("create_constraint_network.py")
    with patch.dict(sys.modules, {"hou": hou}):
        result = network.create_constraint_network(dopnet.path(), constraint_type, relationship_parent=dopnet.path())
    assert result["success"]
    context = result["context"]
    relationship = hou.node(context["relationship_path"])
    created = dopnet.node("constraintnetwork1")
    assert relationship.type().name() == node_type and relationship.parent() is dopnet
    assert [(c.inputIndex(), c.inputItem()) for c in created.inputConnections()] == [(1, relationship)]
    assert context["applied_parameters"] == {} and context["skipped_parameters"] == []
    assert context["simulation_verified"] is False
    assert geo.children() == ()


def test_create_constraint_network_reuses_nodes_and_keeps_sop_geometry_separate():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    geometry = geo.createNode("null", "constraints")
    network = dopnet.createNode("constraintnetwork", "constraintnetwork1")
    network.parms["soppath"] = Parm("soppath", "")
    relationship = dopnet.createNode("glueconrel", "glueconrel")
    source = dopnet.createNode("rbdobject")
    network.setInput(0, source)
    mod = _load("create_constraint_network.py")
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.create_constraint_network(
            dopnet.path(), "glue", relationship_parent=dopnet.path(), parameters={"soppath": geometry.path()}
        )
        again = mod.create_constraint_network(dopnet.path(), "glue", relationship_parent=dopnet.path())
    assert result["success"]
    assert again["success"] and again["context"]["created_network"] is False
    assert result["context"]["applied_parameters"] == {"soppath": geometry.path()}
    assert result["context"]["skipped_parameters"] == []
    assert dopnet.children() == (network, relationship, source)
    assert network.inputs() == (source, relationship)
    assert network.parm("soppath").eval() == geometry.path()


@pytest.mark.parametrize("network_name", ["constraintnetwork1", "glueconrel"])
def test_create_constraint_network_without_relationship_keeps_skeleton_contract(network_name):
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_constraint_network.py").create_constraint_network(
            dopnet.path(), "glue", network_name=network_name
        )
    assert result["success"] and result["context"]["relationship_path"] is None
    assert len(dopnet.children()) == 1 and dopnet.children()[0].inputs() == ()


@pytest.mark.parametrize(
    ("constraint_type", "default_relationship_name"),
    [("glue", "glueconrel"), ("soft", "bulletsoftconrel"), ("cone", "conetwistconrel")],
)
@pytest.mark.parametrize("explicit_name", [False, True])
def test_create_constraint_network_rejects_colliding_names_before_mutation(
    constraint_type, default_relationship_name, explicit_name
):
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    preserved = dopnet.createNode("null", "preserved")
    preserved.parm("size").value = 7
    name = "shared" if explicit_name else default_relationship_name
    with patch.dict(sys.modules, {"hou": hou}), patch.object(dopnet, "createNode", wraps=dopnet.createNode) as create:
        result = _load("create_constraint_network.py").create_constraint_network(
            dopnet.path(),
            constraint_type,
            network_name=name,
            relationship_parent=dopnet.path(),
            relationship_name=name if explicit_name else None,
            parameters={"size": 2},
        )
    assert not result["success"]
    assert "network_name and relationship_name must be different" in skill_error_detail(result)
    create.assert_not_called()
    assert dopnet.children() == (preserved,)
    assert preserved.parm("size").eval() == 7
    assert geo.children() == ()


@pytest.mark.parametrize("parent_kind", ["sop", "foreign_dop"])
def test_create_constraint_network_rejects_invalid_relationship_parent_before_mutation(parent_kind):
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    parent = geo if parent_kind == "sop" else root.createNode("dopnet", "foreign")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_constraint_network.py").create_constraint_network(
            dopnet.path(), "glue", relationship_parent=parent.path()
        )
    assert not result["success"]
    assert dopnet.children() == parent.children() == ()


@pytest.mark.parametrize("conflict", ["network_type", "relationship_type", "occupied_input"])
def test_create_constraint_network_rejects_existing_conflicts(conflict):
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    network = dopnet.createNode("null" if conflict == "network_type" else "constraintnetwork", "constraintnetwork1")
    other = dopnet.createNode("null", "glueconrel" if conflict == "relationship_type" else "other")
    if conflict == "occupied_input":
        network.setInput(1, other)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_constraint_network.py").create_constraint_network(
            dopnet.path(), "glue", relationship_parent=dopnet.path()
        )
    assert not result["success"]
    assert dopnet.children() == (network, other)
    assert network.inputs() == ((other,) if conflict == "occupied_input" else ())


@pytest.mark.parametrize("failure", ["parameter", "wiring", "readback"])
def test_create_constraint_network_rolls_back_new_relationship_and_existing_edits(failure):
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    network = dopnet.createNode("constraintnetwork", "constraintnetwork1")
    source = dopnet.createNode("rbdobject")
    network.setInput(0, source)
    if failure == "parameter":
        network.parm("size").fail_next_set = True
    elif failure == "wiring":
        network.reject_input = True
    else:
        network.errors = lambda: (_ for _ in ()).throw(RuntimeError("readback failed"))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_constraint_network.py").create_constraint_network(
            dopnet.path(), "glue", relationship_parent=dopnet.path(), parameters={"timescale": 0.5, "size": 2}
        )
    assert not result["success"]
    assert dopnet.children() == (network, source)
    assert network.inputs() == (source,)
    assert network.parm("timescale").eval() == network.parm("size").eval() == 1


@pytest.mark.parametrize("constraint_type", ["rope", "wire"])
def test_create_constraint_network_rejects_unknown_type(constraint_type):
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_constraint_network.py").create_constraint_network(dopnet.path(), constraint_type)
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


def test_next_free_input_is_shared_with_domain_graph() -> None:
    """The simulation package no longer keeps a private copy of the helper."""
    from dcc_mcp_houdini import _domain_graph

    common = _load("_simulation_common.py")
    assert not hasattr(common, "next_free_input")
    assert hasattr(_domain_graph, "next_free_input")


def test_create_pyro_source_wires_geometry():
    root, geo, hou = scene()
    sphere = geo.createNode("sphere")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pyro_source.py").create_pyro_source(geo.path(), source_path=sphere.path())
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "pyrosource"
    assert context["source_type"] == "sop"
    assert context["wired"] is True
    assert context["simulation_verified"] is False
    assert hou.node(context["node_path"]).inputs() == (sphere,)


def test_create_pyro_source_supports_volume_source():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pyro_source.py").create_pyro_source(geo.path(), source_type="volume")
    assert result["success"]
    assert result["context"]["node_type"] == "volumesource"
    assert result["context"]["setup_state"] == "unwired"


def test_create_pyro_source_rejects_unknown_source_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pyro_source.py").create_pyro_source(geo.path(), source_type="points")
    assert not result["success"]
    assert "Unsupported source_type" in skill_error_detail(result)
    assert geo.children() == ()


def test_create_pyro_source_requires_sop_parent():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pyro_source.py").create_pyro_source(root.path())
    assert not result["success"]
    assert "Sop" in skill_error_detail(result)


def test_add_pyro_post_process_wires_dop_import():
    root, geo, hou = scene()
    dop_import = geo.createNode("dopimport")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_pyro_post_process.py").add_pyro_post_process(
            geo.path(), source_path=dop_import.path(), parameters={"size": 2}
        )
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "pyropostprocess"
    assert context["wired"] is True
    assert context["applied_parameters"] == {"size": 2}
    assert hou.node(context["node_path"]).inputs() == (dop_import,)


def test_add_gas_field_attaches_to_pyro_solver():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    solver = dopnet.createNode("pyrosolver")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_gas_field.py").add_gas_field(dopnet.path(), "turbulence")
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "gasturbulence"
    assert context["field_type"] == "turbulence"
    assert context["attached_to"] == solver.path()
    assert context["attached_input_index"] == 0
    assert solver.inputs() == (hou.node(context["node_path"]),)


def test_add_gas_field_honours_explicit_connect_to():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    dopnet.createNode("pyrosolver")
    other = dopnet.createNode("gasturbulence")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_gas_field.py").add_gas_field(dopnet.path(), "disturbance", connect_to=other.path())
    assert result["success"]
    assert result["context"]["node_type"] == "gasdisturbance"
    assert result["context"]["attached_to"] == other.path()


def test_add_gas_field_unattached_when_no_solver():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("add_gas_field.py").add_gas_field(dopnet.path(), "resize")
    assert result["success"]
    assert result["context"]["setup_state"] == "unattached"
    assert result["context"]["attached_to"] is None
    assert result["context"]["required_setup"] == ["connect the micro-solver into the solver chain"]


def test_add_gas_field_rejects_unknown_type_and_foreign_target():
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    dopnet.createNode("pyrosolver")
    stray = geo.createNode("null")
    with patch.dict(sys.modules, {"hou": hou}):
        unknown = _load("add_gas_field.py").add_gas_field(dopnet.path(), "smoke")
        foreign = _load("add_gas_field.py").add_gas_field(dopnet.path(), "turbulence", connect_to=stray.path())
    assert not unknown["success"]
    assert "Unsupported field_type" in skill_error_detail(unknown)
    assert not foreign["success"]
    assert "connect_to must name a node inside" in skill_error_detail(foreign)
    assert stray.parent() is geo


def test_solver_helpers_do_not_advertise_skipped_parameters():
    """parameter_edit hard-fails, so these two must not claim a skip path."""
    root, geo, hou = scene()
    network, solver = root.createNode("dopnet"), None
    solver = network.createNode("pyrosolver")
    with patch.dict(sys.modules, {"hou": hou}):
        created = _load("create_simulation_network.py").create_simulation_network(
            root.path(), "pyro", network_name="dopnet1", parameters={"timescale": 2}
        )
        configured = _load("configure_simulation_solver.py").configure_simulation_solver(
            solver.path(), {"timescale": 0.5}
        )
    assert created["success"] and configured["success"]
    assert "skipped_parameters" not in created["context"]
    assert "skipped_parameters" not in configured["context"]


def test_best_effort_defaults_keep_real_skipped_parameters():
    """These three seed optional defaults, so a genuine skip path is correct."""
    root, geo, hou = scene()
    dopnet = root.createNode("dopnet")
    with patch.dict(sys.modules, {"hou": hou}):
        fracture = _load("create_fracture.py").create_fracture(geo.path(), "voronoi")
        constraint = _load("create_constraint_network.py").create_constraint_network(
            dopnet.path(), "glue", relationship_parent=dopnet.path()
        )
        collision = _load("create_collision_source.py").create_collision_source(dopnet.path(), geo.path())
    for result in (fracture, constraint, collision):
        assert result["success"]
        assert "skipped_parameters" in result["context"]


def _forbidden_field_call(*args, **kwargs):
    pytest.fail("Field metadata inspection must not cook, change time, copy geometry, or read voxels")


def _volume(name, resolution=(8, 9, 10), voxel_size=(0.1, 0.2, 0.3)):
    return SimpleNamespace(
        type=lambda: SimpleNamespace(name=lambda: "Volume"),
        attribValue=lambda attrib: name,
        resolution=lambda: resolution,
        voxelSize=lambda: voxel_size,
        voxel=_forbidden_field_call,
        allVoxels=_forbidden_field_call,
        allVoxelsAsString=_forbidden_field_call,
        voxelRange=_forbidden_field_call,
        sample=_forbidden_field_call,
    )


def _dop_data(data_type, components=None, children=None):
    data = SimpleNamespace(dataType=lambda: data_type, children=children or {}, field_reads=[])
    data.subData = lambda: data.children
    data.freeze = _forbidden_field_call
    data.geometry = _forbidden_field_call

    def field_geometry(name):
        data.field_reads.append(name)
        child = data.children[name]
        if isinstance(child.components, Exception):
            raise child.components
        if child.components is None:
            return None
        return SimpleNamespace(
            iterPrims=lambda: iter(child.components),
            findPrimAttrib=lambda name: name,
            merge=_forbidden_field_call,
            freeze=_forbidden_field_call,
        )

    def find_subdata(path):
        current = data
        for name in path.split("/"):
            current = current.children.get(name)
            if current is None:
                break
        return current

    data.fieldGeometry, data.findSubData, data.components = field_geometry, find_subdata, components
    return data


@pytest.fixture
def field_scene():
    root, _, hou = scene()
    network = root.createNode("dopnet")
    obj = _dop_data("SIM_Object", children={"surface": _dop_data("SIM_ScalarField", [_volume("surface")])})
    obj.name, obj.objid = lambda: "water", lambda: 7
    simulation = SimpleNamespace(time=lambda: 0.125, findObject=lambda name: obj if name == "water" else None)
    simulation.setTime = _forbidden_field_call
    network.cookCount, network.needsToCook = lambda: 4, lambda: False
    network.simulation = lambda: simulation
    network.cook = _forbidden_field_call
    hou.frame = lambda: 4.0
    hou.setFrame = hou.setTime = _forbidden_field_call
    return network, hou, simulation, obj


def _inspect_fields(field_scene, **kwargs):
    network, hou, _, _ = field_scene
    arguments = {"network_path": network.path(), "object_name": "water"}
    arguments.update(kwargs)
    with patch.dict(sys.modules, {"hou": hou}):
        return _load("inspect_simulation_fields.py").inspect_simulation_fields(**arguments)


@pytest.mark.parametrize(
    "arguments",
    [
        {"network_path": "relative"},
        {"network_path": "/obj/../dopnet1"},
        {"object_name": "water*"},
        {"object_name": "water/Geometry"},
        {"field_names": "surface"},
        {"field_names": []},
        {"field_names": ["surface"] * 33},
        {"field_names": ["surface", "surface"]},
        {"field_names": ["../surface"]},
        {"field_names": ["/surface"]},
        {"field_names": ["surface\n"]},
        {"field_names": ["vel?"]},
        {"max_fields": 0},
        {"max_fields": 33},
        {"max_fields": True},
        {"max_fields": 1.5},
    ],
)
def test_inspect_fields_rejects_invalid_arguments_before_hom(field_scene, arguments):
    _, hou, _, _ = field_scene
    with patch.object(hou, "node", side_effect=_forbidden_field_call):
        assert not _inspect_fields(field_scene, **arguments)["success"]


@pytest.mark.parametrize("guard", ["uncooked", "dirty", "missing", "raises", "unknown"])
def test_inspect_fields_rejects_unsafe_network_before_simulation(field_scene, guard):
    network, _, _, _ = field_scene
    if guard == "uncooked":
        network.cookCount = lambda: 0
    elif guard == "dirty":
        network.needsToCook = lambda: True
    elif guard == "missing":
        del network.needsToCook
    elif guard == "raises":
        network.needsToCook = lambda: (_ for _ in ()).throw(RuntimeError("guard unavailable"))
    else:
        network.needsToCook = lambda: None
    with patch.object(network, "simulation", side_effect=_forbidden_field_call):
        assert not _inspect_fields(field_scene)["success"]


def test_inspect_fields_preserves_scalar_vector_and_staggered_metadata(field_scene):
    _, _, _, obj = field_scene
    obj.children["vel"] = _dop_data("SIM_VectorField", [_volume("vel." + axis) for axis in "xyz"])
    staggered = [(9, 9, 10), (8, 10, 10), (8, 9, 11)]
    obj.children["collisionweights"] = _dop_data(
        "SIM_VectorField", [_volume("weight." + str(index), size) for index, size in enumerate(staggered)]
    )
    result = _inspect_fields(field_scene, field_names=["surface", "vel", "collisionweights"])
    assert result["success"]
    context = result["context"]
    assert context["object_id"] == 7 and context["object_name"] == "water"
    assert context["before"] == context["after"] == {"frame": 4.0, "cook_count": 4, "simulation_time": 0.125}
    scalar, vector, weights = context["fields"]
    assert scalar == {
        "name": "surface",
        "data_type": "SIM_ScalarField",
        "status": "ok",
        "components": [
            {"name": "surface", "primitive_type": "Volume", "resolution": [8, 9, 10], "voxel_size": [0.1, 0.2, 0.3]}
        ],
    }
    assert [component["name"] for component in vector["components"]] == ["vel.x", "vel.y", "vel.z"]
    assert [component["resolution"] for component in weights["components"]] == [list(size) for size in staggered]


def test_inspect_fields_exact_paths_and_entry_bound(field_scene):
    _, _, _, obj = field_scene
    group = _dop_data("SIM_Data", children={"pressure": _dop_data("SIM_ScalarField", [_volume("pressure")])})
    obj.children["nested"] = group
    explicit = _inspect_fields(field_scene, field_names=["nested/pressure", "surface"], max_fields=1)["context"]
    assert explicit["fields"][0]["name"] == "nested/pressure"
    assert explicit["total_entries"] == 2 and explicit["truncated"] is True
    assert group.field_reads == ["pressure"] and obj.field_reads == []
    direct = _inspect_fields(field_scene, max_fields=1)["context"]
    assert direct["fields"] == [{"name": "nested", "data_type": "SIM_Data", "status": "not_field"}]
    assert direct["total_entries"] == 2 and direct["truncated"] is True
    assert group.field_reads == ["pressure"]


def test_inspect_fields_distinguishes_missing_nonfield_and_read_errors(field_scene):
    _, _, _, obj = field_scene
    obj.children["Geometry"] = _dop_data("SIM_Geometry")
    obj.children["broken"] = _dop_data("SIM_ScalarField", RuntimeError("field unavailable"))
    result = _inspect_fields(field_scene, field_names=["absent", "Geometry", "broken"])
    assert result["success"]
    fields = result["context"]["fields"]
    assert [field["status"] for field in fields] == ["missing", "not_field", "read_error"]
    assert fields[2]["error"] == "field unavailable" and fields[2]["error_type"] == "RuntimeError"


def test_inspect_fields_component_bound_is_an_explicit_read_error(field_scene):
    _, _, _, obj = field_scene

    def components():
        yield from (_volume(str(index)) for index in range(17))
        pytest.fail("Must not read beyond the component limit sentinel")

    obj.children["large"] = _dop_data("SIM_MatrixField", components())
    result = _inspect_fields(field_scene, field_names=["large"])
    assert result["success"]
    field = result["context"]["fields"][0]
    assert field["status"] == "read_error" and "16-component" in field["error"]
    assert "components" not in field


@pytest.mark.parametrize("state", ["frame", "cook_count", "simulation_time"])
def test_inspect_fields_fails_when_state_changes_during_read(field_scene, state):
    network, hou, simulation, obj = field_scene
    original = obj.fieldGeometry

    def changed(name):
        if state == "frame":
            hou.frame = lambda: 5.0
        elif state == "cook_count":
            network.cookCount = lambda: 5
        else:
            simulation.time = lambda: 0.25
        return original(name)

    obj.fieldGeometry = changed
    result = _inspect_fields(field_scene)
    assert not result["success"]
    assert result["context"]["before"][state] != result["context"]["after"][state]


def test_inspect_fields_detects_cook_during_simulation_access(field_scene):
    network, _, simulation, obj = field_scene

    def changed():
        network.cookCount = lambda: 5
        return simulation

    network.simulation = changed
    result = _inspect_fields(field_scene)
    assert not result["success"] and obj.field_reads == []
    assert result["context"]["after"]["cook_count"] == 5


def test_inspect_fields_requires_exact_existing_object(field_scene):
    assert not _inspect_fields(field_scene, object_name="missing")["success"]
    field_scene[2].findObject = lambda name: field_scene[3]
    result = _inspect_fields(field_scene, object_name="other")
    assert not result["success"] and "exact requested name" in skill_error_detail(result)


def test_inspect_fields_is_discoverable_without_importing_hou(monkeypatch):
    import dcc_mcp_core

    monkeypatch.setenv("DCC_MCP_DISABLE_DEFAULT_SKILL_PATHS", "1")
    catalog = dcc_mcp_core.SkillCatalog(dcc_mcp_core.ToolRegistry())
    catalog.set_in_process_executor(_forbidden_field_call)
    assert catalog.discover(extra_paths=[str(_ROOT.parent)], dcc_name="houdini") >= 1
    assert any(skill.name == "houdini-simulation" for skill in catalog.search_skills(query="field metadata"))
    assert "houdini_simulation__inspect_simulation_fields" in catalog.load_skill("houdini-simulation")
    tool = next(
        tool for tool in catalog.get_skill("houdini-simulation").tools if tool.name == "inspect_simulation_fields"
    )
    assert json.loads(tool.input_schema)["properties"]["max_fields"]["maximum"] == 32
    assert tool.next_tools == {"on_success": [], "on_failure": ["houdini_simulation__inspect_simulation_network"]}
