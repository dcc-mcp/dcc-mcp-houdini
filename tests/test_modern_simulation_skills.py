"""Public contracts for the four modern Houdini node families (PIP-5118).

RBD material fracture, COps pyro, sparse GPU pyro and rasterize Volume are
exposed through a host-independent catalog, a read-only planning tool and a
typed creator. These tests use the project's explicit fake-``hou`` harness and
pure stdlib, so they are fully reproducible without a Houdini install and stay
on the project's Python 3.7 baseline. They cover the alias/plan layer, the
planning tool, and the scene-touching create tool (create / wire / rollback /
category enforcement) end to end.

The mapped node types and recommended parameter names were confirmed against a
live Houdini 22.0.368 host (see the SKILL.md "Modern Houdini node families"
section); no live host is required to run these tests.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from domain_graph_fakes import scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-simulation"


def _load(name):
    spec = importlib.util.spec_from_file_location("modernsim_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _sop_network():
    """Return (root, geo, hou) where ``geo`` has a Sop child category."""
    return scene()


def _cop_network():
    root, geo, hou = scene()
    return root, geo, hou, geo.createNode("copnet")


def _dop_network():
    root, geo, hou = scene()
    return root, geo, hou, root.createNode("dopnet")


def _parent_for(category):
    if category == "Sop":
        _root, geo, hou = _sop_network()
        return geo, hou
    if category == "Cop":
        _root, _geo, hou, net = _cop_network()
        return net, hou
    if category == "Dop":
        _root, _geo, hou, net = _dop_network()
        return net, hou
    raise AssertionError("unexpected category " + str(category))


# ---------------------------------------------------------------------------
# _modern_sim.py: pure alias / plan layer (no host access)
# ---------------------------------------------------------------------------

EXPECTED_FAMILIES = (
    "rbd_material_fracture",
    "cops_pyro",
    "sparse_gpu_pyro",
    "rasterize_volume",
)


def test_families_are_stable_and_complete():
    mod = _load("_modern_sim.py")
    assert mod.FAMILIES == EXPECTED_FAMILIES
    # every declared family has aliases, recommended params, a chain and setup
    for family in mod.FAMILIES:
        assert mod.aliases_for_family(family)
        assert mod.RECOMMENDED_PARAMETERS[family]
        assert mod.FAMILY_CHAINS[family]


def test_every_alias_resolves_and_has_valid_shape():
    mod = _load("_modern_sim.py")
    for alias, meta in mod.MODERN_SIM_NODES.items():
        assert set(meta) == {"node_type", "category", "family"}
        assert meta["category"] in {"Sop", "Cop", "Dop"}
        assert meta["family"] in mod.FAMILIES
        assert mod.resolve_modern_node(alias) == meta["node_type"]
        assert mod.modern_node_category(alias) == meta["category"]
        assert mod.modern_node_family(alias) == meta["family"]


@pytest.mark.parametrize(
    "alias,node_type,category,family",
    [
        ("rbd_material_fracture", "rbdmaterialfracture", "Sop", "rbd_material_fracture"),
        ("rbd_glass_fracture", "rbdglassfracture", "Sop", "rbd_material_fracture"),
        ("pyro_configure", "pyro_configure", "Cop", "cops_pyro"),
        ("pyro_source_volume", "pyro_sourcefromvolume", "Cop", "cops_pyro"),
        ("pyro_sparse_solver", "pyrosolver_sparse", "Dop", "sparse_gpu_pyro"),
        ("gas_opencl", "gasopencl", "Dop", "sparse_gpu_pyro"),
        ("rasterize_volume", "rasterizevolume", "Cop", "rasterize_volume"),
        ("volume_rasterize", "volumerasterize", "Sop", "rasterize_volume"),
    ],
)
def test_representative_aliases_across_all_four_families(alias, node_type, category, family):
    mod = _load("_modern_sim.py")
    meta = mod.modern_node_meta(alias)
    assert meta["node_type"] == node_type
    assert meta["category"] == category
    assert meta["family"] == family


@pytest.mark.parametrize(
    "raw",
    ["rbdmaterialfracture", "pyro_sourcefromvolume", "pyrosolver_sparse", "rasterizevolume"],
)
def test_raw_node_types_are_accepted(raw):
    mod = _load("_modern_sim.py")
    assert mod.resolve_modern_node(raw) == raw
    assert mod.modern_node_meta(raw)["node_type"] == raw


@pytest.mark.parametrize("bad", ["volcano", "pyro_magic", "rbdfracture"])
def test_unknown_alias_raises_with_supported_set(bad):
    mod = _load("_modern_sim.py")
    with pytest.raises(ValueError) as excinfo:
        mod.resolve_modern_node(bad)
    assert "Unsupported modern simulation node" in str(excinfo.value)
    assert "pyro_configure" in str(excinfo.value)


@pytest.mark.parametrize("bad", ["", "   ", None, 3, [], {}])
def test_non_string_or_empty_alias_raises(bad):
    mod = _load("_modern_sim.py")
    with pytest.raises(ValueError) as excinfo:
        mod.modern_node_meta(bad)
    assert "non-empty string" in str(excinfo.value)


def test_aliases_for_family_matches_declared_nodes():
    mod = _load("_modern_sim.py")
    for family in mod.FAMILIES:
        aliases = mod.aliases_for_family(family)
        assert aliases == tuple(a for a, m in mod.MODERN_SIM_NODES.items() if m["family"] == family)
    with pytest.raises(ValueError):
        mod.aliases_for_family("not_a_family")


def test_rasterize_volume_family_spans_cop_and_sop():
    mod = _load("_modern_sim.py")
    categories = {mod.modern_node_category(a) for a in mod.aliases_for_family("rasterize_volume")}
    assert categories == {"Cop", "Sop"}


def test_build_plan_is_deterministic_and_json_safe():
    mod = _load("_modern_sim.py")
    for family in mod.FAMILIES:
        a = mod.build_modern_sim_plan(family)
        b = mod.build_modern_sim_plan(family)
        assert a == b
        assert json.loads(json.dumps(a)) == a
        assert a["family"] == family
        assert a["step_count"] == len(a["steps"]) == len(mod.FAMILY_CHAINS[family])
        assert a["aliases"] == list(mod.aliases_for_family(family))
        assert a["validation_scope"] == "plan_only_no_host_access"
        assert a["artifact_verified"] is False
        assert a["simulation_verified"] is False
        assert a["required_setup"]


def test_plan_steps_resolve_node_types_and_categories():
    mod = _load("_modern_sim.py")
    for family in mod.FAMILIES:
        plan = mod.build_modern_sim_plan(family)
        for step in plan["steps"]:
            if step["alias"] is None:
                assert step["node_type"] is None
                assert step["category"] is None
            else:
                meta = mod.modern_node_meta(step["alias"])
                assert step["node_type"] == meta["node_type"]
                assert step["category"] == meta["category"]


def test_recommended_parameters_are_guidance_not_applied_defaults():
    mod = _load("_modern_sim.py")
    for family in mod.FAMILIES:
        for item in mod.RECOMMENDED_PARAMETERS[family]:
            assert set(item) == {"name", "purpose", "typical"}
    plan = mod.build_modern_sim_plan("cops_pyro")
    # mutating the returned plan must not corrupt subsequent plans (deep copy)
    plan["recommended_parameters"].clear()
    plan["required_setup"].append("injected")
    plan["steps"].clear()
    again = mod.build_modern_sim_plan("cops_pyro")
    assert again["recommended_parameters"]
    assert "injected" not in again["required_setup"]
    assert again["steps"]
    assert again["step_count"] == len(again["steps"])


def test_build_plan_rejects_unknown_family():
    mod = _load("_modern_sim.py")
    with pytest.raises(ValueError) as excinfo:
        mod.build_modern_sim_plan("fluids")
    assert "Unsupported modern simulation family" in str(excinfo.value)


def test_catalog_sources_are_py37_parseable():
    import ast

    for name in ("_modern_sim.py", "plan_modern_simulation.py", "create_modern_sim_node.py"):
        source = (_ROOT / "scripts" / name).read_text(encoding="utf-8")
        ast.parse(source, filename=name, feature_version=(3, 7))


# ---------------------------------------------------------------------------
# plan_modern_simulation.py: read-only planning tool (no hou)
# ---------------------------------------------------------------------------


def test_plan_tool_lists_families_without_hou():
    result = _load("plan_modern_simulation.py").plan_modern_simulation()
    assert result["success"]
    ctx = result["context"]
    assert ctx["families"] == list(EXPECTED_FAMILIES)
    assert ctx["family_count"] == 4
    assert ctx["validation_scope"] == "catalog_only_no_host_access"
    assert ctx["artifact_verified"] is False
    assert ctx["simulation_verified"] is False
    # No-arg listing must expose each family's aliases (docs promise this, so an
    # agent can discover the vocabulary without four follow-up per-family calls).
    aliases = ctx["aliases"]
    assert set(aliases) == set(EXPECTED_FAMILIES)
    for family in EXPECTED_FAMILIES:
        assert aliases[family] == list(_load("_modern_sim.py").aliases_for_family(family))
        assert aliases[family]


@pytest.mark.parametrize("family", EXPECTED_FAMILIES)
def test_plan_tool_returns_plan_for_each_family(family):
    result = _load("plan_modern_simulation.py").plan_modern_simulation(family)
    assert result["success"]
    ctx = result["context"]
    assert ctx["family"] == family
    assert ctx["plan"]["family"] == family
    assert ctx["step_count"] == ctx["plan"]["step_count"]
    assert ctx["aliases"]
    assert ctx["validation_scope"] == "plan_only_no_host_access"
    assert ctx["artifact_verified"] is False
    assert ctx["simulation_verified"] is False


def test_plan_tool_rejects_unknown_family():
    result = _load("plan_modern_simulation.py").plan_modern_simulation("nucleus")
    assert not result["success"]
    assert "Unsupported modern simulation family" in skill_error_detail(result)


@pytest.mark.parametrize("bad", [3, [], {"a": 1}])
def test_plan_tool_rejects_non_string_family(bad):
    result = _load("plan_modern_simulation.py").plan_modern_simulation(bad)
    assert not result["success"]
    assert "family must be a string" in skill_error_detail(result)


def test_plan_tool_never_imports_hou():
    # The planning tool must be pure: even with a hostile hou module it works.
    with patch.dict(sys.modules, {"hou": None}):
        result = _load("plan_modern_simulation.py").plan_modern_simulation("cops_pyro")
    assert result["success"]


# ---------------------------------------------------------------------------
# create_modern_sim_node.py: typed creator (create / wire / rollback)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias,node_type,category,family",
    [
        ("rbd_material_fracture", "rbdmaterialfracture", "Sop", "rbd_material_fracture"),
        ("rbd_concrete_fracture", "rbdconcretefracture", "Sop", "rbd_material_fracture"),
        ("pyro_configure", "pyro_configure", "Cop", "cops_pyro"),
        ("pyro_block_begin", "pyro_block_begin", "Cop", "cops_pyro"),
        ("pyro_sparse_solver", "pyrosolver_sparse", "Dop", "sparse_gpu_pyro"),
        ("smoke_sparse_object", "smokeobject_sparse", "Dop", "sparse_gpu_pyro"),
        ("rasterize_volume", "rasterizevolume", "Cop", "rasterize_volume"),
        ("volume_rasterize", "volumerasterize", "Sop", "rasterize_volume"),
    ],
)
def test_creator_resolves_alias_in_matching_network(alias, node_type, category, family):
    parent, hou = _parent_for(category)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(parent.path(), alias)
    assert result["success"], skill_error_detail(result)
    ctx = result["context"]
    assert ctx["node_type"] == node_type
    assert ctx["resolved_node_type"] == node_type
    assert ctx["requested_node_type"] == alias
    assert ctx["category"] == category
    assert ctx["family"] == family
    assert ctx["setup_state"] == "unwired"
    assert ctx["artifact_verified"] is False
    assert ctx["simulation_verified"] is False
    assert any("cook" in step for step in ctx["required_setup"])
    assert parent.node(alias + "1") is not None or any(c.type().name() == node_type for c in parent.children())


@pytest.mark.parametrize(
    "raw,node_type,category",
    [
        ("rbdmaterialfracture", "rbdmaterialfracture", "Sop"),
        ("pyrosolver_sparse", "pyrosolver_sparse", "Dop"),
    ],
)
def test_creator_accepts_raw_node_type(raw, node_type, category):
    parent, hou = _parent_for(category)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(parent.path(), raw)
    assert result["success"]
    assert result["context"]["node_type"] == node_type


def test_creator_applies_parameters_and_reads_back():
    parent, hou = _parent_for("Sop")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(
            parent.path(), "rbd_material_fracture", parameters={"size": 4}
        )
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"size": 4}


def test_creator_wires_inputs_and_reads_back():
    _root, _geo, hou, net = _cop_network()
    source = net.createNode("pyro_source_volume")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(
            net.path(), "pyro_configure", input_nodes=[source.path()]
        )
    assert result["success"], skill_error_detail(result)
    assert result["context"]["setup_state"] == "wired"
    assert result["context"]["wired_inputs"] == [
        {"input_index": 0, "source_path": source.path(), "source_output_index": 0}
    ]


def test_creator_rolls_back_on_unknown_parameter():
    parent, hou = _parent_for("Dop")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(
            parent.path(), "pyro_sparse_solver", parameters={"nope": 1}
        )
    assert not result["success"]
    assert parent.children() == ()


def test_creator_rejects_unknown_alias_without_creating_node():
    parent, hou = _parent_for("Cop")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(parent.path(), "pyro_magic")
    assert not result["success"]
    assert "Unsupported modern simulation node" in skill_error_detail(result)
    assert parent.children() == ()


def test_creator_enforces_parent_category():
    # A Sop-parent (geo) cannot host a Cop pyro node; a Cop parent cannot host a
    # Dop sparse solver; a Dop parent cannot host a Sop fracture node.
    cases = [
        ("Sop", "pyro_configure"),
        ("Cop", "pyro_sparse_solver"),
        ("Dop", "rbd_material_fracture"),
    ]
    for parent_category, alias in cases:
        parent, hou = _parent_for(parent_category)
        with patch.dict(sys.modules, {"hou": hou}):
            result = _load("create_modern_sim_node.py").create_modern_sim_node(parent.path(), alias)
        assert not result["success"], (parent_category, alias)
        assert "category" in skill_error_detail(result).lower()
        assert parent.children() == ()


def test_creator_rejects_cross_network_input():
    _root, _geo, hou, net = _cop_network()
    other = net.parent().createNode("copnet", "other")
    source = other.createNode("pyro_source_from_layer")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(
            net.path(), "pyro_configure", input_nodes=[source.path()]
        )
    assert not result["success"]
    assert net.children() == ()


def test_creator_hou_missing_returns_structured_error():
    _root, geo, _hou = _sop_network()
    assert "hou" not in sys.modules
    result = _load("create_modern_sim_node.py").create_modern_sim_node(geo.path(), "rbd_material_fracture")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


def test_creator_requires_absolute_parent_path():
    _root, geo, hou = _sop_network()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node("geo1", "rbd_material_fracture")
    assert not result["success"]
    assert "absolute" in skill_error_detail(result).lower()


def test_creator_rejects_invalid_parameters_before_creating_node():
    parent, hou = _parent_for("Sop")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_modern_sim_node.py").create_modern_sim_node(
            parent.path(), "rbd_material_fracture", parameters={"size": float("nan")}
        )
    assert not result["success"]
    assert parent.children() == ()
