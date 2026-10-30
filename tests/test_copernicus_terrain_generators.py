"""Public contracts for Copernicus COP terrain generators (fractal sample / strata).

These tests use the project's explicit fake-``hou`` harness and pure stdlib, so
they are fully reproducible without a Houdini install and stay on the project's
Python 3.7 baseline. They cover the host-independent planning/alias layer and
the scene-touching create tool (create/wire/rollback) end to end.
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

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-copernicus"


def _load(name):
    spec = importlib.util.spec_from_file_location("copterrain_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# _cop_terrain.py: pure alias / plan layer (no host access)
# ---------------------------------------------------------------------------


def test_generator_type_map_is_stable():
    mod = _load("_cop_terrain.py")
    assert mod.TERRAIN_GENERATOR_TYPES == {
        "fractal_sample": "fractalsample",
        "fractal_noise": "fractalnoise",
        "fractal_noise_3d": "fractalnoise3d",
        "strata": "heightfield_strata",
        "heightfield_strata": "heightfield_strata",
    }
    assert mod.FRACTAL_SAMPLE_ALIASES == {"fractal_sample", "fractal_noise", "fractal_noise_3d"}
    assert mod.STRATA_ALIASES == {"strata", "heightfield_strata"}


@pytest.mark.parametrize(
    "alias,node_type",
    [
        ("fractal_sample", "fractalsample"),
        ("fractal_noise", "fractalnoise"),
        ("fractal_noise_3d", "fractalnoise3d"),
        ("strata", "heightfield_strata"),
        ("heightfield_strata", "heightfield_strata"),
    ],
)
def test_resolve_terrain_generator_accepts_all_aliases(alias, node_type):
    mod = _load("_cop_terrain.py")
    assert mod.resolve_terrain_generator(alias) == node_type


@pytest.mark.parametrize("raw", ["fractalsample", "fractalnoise", "fractalnoise3d", "heightfield_strata"])
def test_resolve_terrain_generator_accepts_raw_node_types(raw):
    mod = _load("_cop_terrain.py")
    assert mod.resolve_terrain_generator(raw) == raw


@pytest.mark.parametrize("bad", ["volcano", "heightfield_noise"])
def test_resolve_terrain_generator_rejects_unknown(bad):
    mod = _load("_cop_terrain.py")
    with pytest.raises(ValueError) as excinfo:
        mod.resolve_terrain_generator(bad)
    assert "Unsupported terrain generator" in str(excinfo.value)
    assert "fractal_sample" in str(excinfo.value)


@pytest.mark.parametrize("bad", ["", None, 3])
def test_resolve_terrain_generator_rejects_non_string(bad):
    mod = _load("_cop_terrain.py")
    with pytest.raises(ValueError) as excinfo:
        mod.resolve_terrain_generator(bad)
    assert "non-empty string" in str(excinfo.value)


@pytest.mark.parametrize(
    "alias,family",
    [
        ("fractal_sample", "fractal_sample"),
        ("fractal_noise", "fractal_sample"),
        ("fractalnoise", "fractal_sample"),
        ("strata", "strata"),
        ("heightfield_strata", "strata"),
    ],
)
def test_generator_family(alias, family):
    mod = _load("_cop_terrain.py")
    assert mod.generator_family(alias) == family


def test_generator_family_rejects_unknown():
    mod = _load("_cop_terrain.py")
    with pytest.raises(ValueError):
        mod.generator_family("volcano")


def test_build_terrain_plan_is_deterministic_and_json_safe():
    mod = _load("_cop_terrain.py")
    first = mod.build_terrain_plan("fractal_noise")
    second = mod.build_terrain_plan("fractal_noise")
    assert first == second
    # JSON-safe: a plan is meant to cross the MCP/REST boundary.
    assert json.loads(json.dumps(first)) == first
    assert first["artifact_verified"] is False
    assert first["validation_scope"] == "plan_only_no_host_access"
    assert first["family"] == "fractal_sample"
    assert first["node_type"] == "fractalnoise"
    assert first["step_count"] == len(first["steps"]) == 6


def test_build_terrain_plan_roles_follow_proven_chain():
    mod = _load("_cop_terrain.py")
    plan = mod.build_terrain_plan("fractal_noise")
    node_types = [step["node_type"] for step in plan["steps"]]
    assert node_types == [
        "fractalnoise",
        "mono",
        "monotoheightfield",
        "heightfield_strata",
        "heightfieldtomono",
        "rop_image",
    ]
    roles = [step["role"] for step in plan["steps"]]
    assert roles == ["source", "to_mono", "to_heightfield", "strata", "from_heightfield", "output"]
    assert any("cook" in step for step in plan["required_setup"])
    assert any("inspect_cop_output" in step for step in plan["required_setup"])


@pytest.mark.parametrize(
    "generator,node_type,alias",
    [
        ("fractal_sample", "fractalsample", "fractal_sample"),
        ("fractal_noise", "fractalnoise", "fractal_noise"),
        ("fractal_noise_3d", "fractalnoise3d", "fractal_noise_3d"),
        # Raw node types are accepted too; the head alias is still canonical.
        ("fractalsample", "fractalsample", "fractal_sample"),
        ("fractalnoise3d", "fractalnoise3d", "fractal_noise_3d"),
    ],
)
def test_build_terrain_plan_head_uses_selected_generator(generator, node_type, alias):
    mod = _load("_cop_terrain.py")
    source = mod.build_terrain_plan(generator)["steps"][0]
    assert source["node_type"] == node_type
    # F1: the source alias must match the selected generator, not a hardcoded value.
    assert source["alias"] == alias
    assert mod.resolve_terrain_generator(source["alias"]) == source["node_type"]


def test_build_terrain_plan_source_alias_tracks_generator_across_heads():
    mod = _load("_cop_terrain.py")
    aliases = [
        mod.build_terrain_plan(g)["steps"][0]["alias"] for g in ("fractal_sample", "fractal_noise", "fractal_noise_3d")
    ]
    # Distinct generators must not collapse to one stale alias.
    assert aliases == ["fractal_sample", "fractal_noise", "fractal_noise_3d"]


def test_build_terrain_plan_non_source_steps_keep_template_alias():
    mod = _load("_cop_terrain.py")
    steps = mod.build_terrain_plan("fractal_sample")["steps"]
    # Only the head is dynamic; the strata/output steps keep template aliases.
    assert steps[3]["role"] == "strata"
    assert steps[3]["alias"] == "strata"
    assert steps[-1]["role"] == "output"
    assert steps[-1]["alias"] is None
    # Only the source step carries the fractal-sample parameter hints.
    assert steps[0]["parameters_hint"]
    assert any(item["name"] == "freq" for item in steps[0]["parameters_hint"])
    assert all(step["parameters_hint"] == [] for step in steps[1:])


def test_build_terrain_plan_flags_toggle_optional_steps():
    mod = _load("_cop_terrain.py")
    no_strata = mod.build_terrain_plan("fractal_noise", with_strata=False)
    assert "heightfield_strata" not in [s["node_type"] for s in no_strata["steps"]]
    assert no_strata["step_count"] == 5
    minimal = mod.build_terrain_plan("fractal_noise", with_strata=False, with_output=False)
    assert "rop_image" not in [s["node_type"] for s in minimal["steps"]]
    assert minimal["step_count"] == 4


def test_recommended_parameters_are_guidance_not_applied_defaults():
    mod = _load("_cop_terrain.py")
    plan = mod.build_terrain_plan("fractal_noise")
    assert "fractal_sample" in plan["recommended_parameters"]
    assert "strata" in plan["recommended_parameters"]
    # Guidance is descriptive metadata; no step auto-applies raw parameters.
    for step in plan["steps"]:
        assert "applied_parameters" not in step


def test_build_terrain_plan_rejects_unknown_generator():
    mod = _load("_cop_terrain.py")
    with pytest.raises(ValueError) as excinfo:
        mod.build_terrain_plan("volcano")
    assert "Unsupported terrain generator" in str(excinfo.value)


def test_build_terrain_plan_rejects_strata_as_head():
    # strata is a mid-chain layer; it cannot be the chain's fractal-noise source.
    mod = _load("_cop_terrain.py")
    with pytest.raises(ValueError) as excinfo:
        mod.build_terrain_plan("strata")
    assert "fractal-sample generator" in str(excinfo.value)


# ---------------------------------------------------------------------------
# plan_fractal_terrain.py: host-independent skill tool (no hou)
# ---------------------------------------------------------------------------


def test_plan_tool_succeeds_without_hou():
    # This test deliberately does not patch sys.modules["hou"]: the tool is pure.
    result = _load("plan_fractal_terrain.py").plan_fractal_terrain()
    assert result["success"]
    context = result["context"]
    assert context["artifact_verified"] is False
    assert context["validation_scope"] == "plan_only_no_host_access"
    assert context["generator"] == "fractal_noise"
    assert context["node_type"] == "fractalnoise"
    assert context["step_count"] == 6
    assert context["plan"]["steps"][0]["node_type"] == "fractalnoise"


def test_plan_tool_custom_generator_and_flags():
    mod = _load("plan_fractal_terrain.py")
    result = mod.plan_fractal_terrain(generator="fractal_sample", with_strata=False, with_output=False)
    assert result["success"]
    assert result["context"]["family"] == "fractal_sample"
    assert result["context"]["node_type"] == "fractalsample"
    assert result["context"]["step_count"] == 4


@pytest.mark.parametrize("kwargs", [{"with_strata": "no"}, {"with_output": 1}, {"with_strata": None}])
def test_plan_tool_rejects_non_boolean_flags(kwargs):
    result = _load("plan_fractal_terrain.py").plan_fractal_terrain(**kwargs)
    assert not result["success"]
    assert "booleans" in skill_error_detail(result)


def test_plan_tool_reports_unknown_generator():
    result = _load("plan_fractal_terrain.py").plan_fractal_terrain(generator="volcano")
    assert not result["success"]
    assert "Unsupported terrain generator" in skill_error_detail(result)


def test_plan_tool_has_no_traceback_on_plain_validation_error():
    result = _load("plan_fractal_terrain.py").plan_fractal_terrain(generator="volcano")
    assert "traceback" not in result["context"]


# ---------------------------------------------------------------------------
# create_terrain_generator.py: scene-touching tool via fake hou
# ---------------------------------------------------------------------------


def _cop_network():
    return scene()


def test_create_generator_resolves_alias_and_reports_family():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_terrain_generator.py").create_terrain_generator(network.path(), "fractal_noise")
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "fractalnoise"
    assert context["generator_type"] == "fractal_noise"
    assert context["family"] == "fractal_sample"
    assert context["setup_state"] == "unwired"
    assert context["artifact_verified"] is False
    assert any("cook" in step for step in context["required_setup"])


@pytest.mark.parametrize(
    "generator,node_type,family",
    [
        ("fractal_sample", "fractalsample", "fractal_sample"),
        ("fractal_noise_3d", "fractalnoise3d", "fractal_sample"),
        ("strata", "heightfield_strata", "strata"),
        ("heightfield_strata", "heightfield_strata", "strata"),
    ],
)
def test_create_generator_all_families(generator, node_type, family):
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_terrain_generator.py").create_terrain_generator(network.path(), generator)
    assert result["success"]
    assert result["context"]["node_type"] == node_type
    assert result["context"]["family"] == family


def test_create_generator_applies_parameters_and_reads_back():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_terrain_generator.py").create_terrain_generator(
            network.path(), "fractal_noise", parameters={"size": 4}
        )
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"size": 4}


def test_create_generator_wires_inputs_and_reads_back():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    source = network.createNode("mono")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_terrain_generator.py").create_terrain_generator(
            network.path(), "strata", input_nodes=[source.path()]
        )
    assert result["success"]
    assert result["context"]["setup_state"] == "wired"
    assert result["context"]["wired_inputs"] == [
        {"input_index": 0, "source_path": source.path(), "source_output_index": 0}
    ]


def test_create_generator_rolls_back_on_unknown_parameter():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_terrain_generator.py").create_terrain_generator(
            network.path(), "fractal_noise", parameters={"nope": 1}
        )
    assert not result["success"]
    assert network.children() == ()


def test_create_generator_rejects_unknown_generator_without_creating_node():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_terrain_generator.py").create_terrain_generator(network.path(), "volcano")
    assert not result["success"]
    assert "Unsupported terrain generator" in skill_error_detail(result)
    assert network.children() == ()


def test_create_generator_rejects_cross_network_input():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    other = geo.createNode("copnet", "other")
    source = other.createNode("mono")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_terrain_generator.py").create_terrain_generator(
            network.path(), "strata", input_nodes=[source.path()]
        )
    assert not result["success"]
    assert network.children() == ()


def test_create_generator_hou_missing_returns_structured_error():
    root, geo, _hou = _cop_network()
    network_path = geo.createNode("copnet").path()
    assert "hou" not in sys.modules
    result = _load("create_terrain_generator.py").create_terrain_generator(network_path, "strata")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


# ---------------------------------------------------------------------------
# resolve_filter_type wiring: aliases usable by existing authoring tools
# ---------------------------------------------------------------------------


def test_resolve_filter_type_knows_terrain_aliases():
    mod = _load("_cop_common.py")
    assert mod.resolve_filter_type("fractal_sample") == "fractalsample"
    assert mod.resolve_filter_type("fractal_noise") == "fractalnoise"
    assert mod.resolve_filter_type("strata") == "heightfield_strata"
    assert mod.resolve_filter_type("heightfield_strata") == "heightfield_strata"


def test_create_cop_node_accepts_terrain_alias():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_cop_node.py").create_cop_node(network.path(), "strata")
    assert result["success"]
    assert result["context"]["node_type"] == "heightfield_strata"


def test_build_composite_chain_accepts_terrain_alias():
    root, geo, hou = _cop_network()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("build_composite_chain.py").build_composite_chain(
            network.path(),
            steps=[{"filter_type": "fractal_noise"}, {"filter_type": "strata"}],
        )
    assert result["success"]
    assert [item["node_type"] for item in result["context"]["nodes"]] == ["fractalnoise", "heightfield_strata"]
