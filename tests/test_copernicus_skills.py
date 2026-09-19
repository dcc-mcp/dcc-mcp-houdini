"""Public domain tool contracts with explicit HOM doubles."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from domain_graph_fakes import Node, scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-copernicus"


def _load(name):
    spec = importlib.util.spec_from_file_location("copernicus_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_create_cop_network_is_idempotent_and_modern():
    root, geo, hou = scene()
    mod = _load("create_cop_network.py")
    with patch.dict(sys.modules, {"hou": hou}):
        first = mod.create_cop_network(geo.path())
        second = mod.create_cop_network(geo.path())
    assert first["success"] and second["success"]
    assert first["context"]["created"] and not second["context"]["created"]
    assert geo.node("copnet1").type().name() == "copnet"


def test_reuse_rejects_legacy_cop2():
    root, geo, hou = scene()
    old = Node(geo.path() + "/copnet1", "cop2net", geo, "Cop2")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_cop_network.py").create_cop_network(geo.path())
    assert not result["success"]
    assert not old.destroyed


def test_create_cop_node_wires_and_reads_parameters():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    source = network.createNode("file")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_cop_node.py").create_cop_node(
            network.path(), "blur", input_nodes=[source.path()], parameters={"size": 4}
        )
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"size": 4}
    assert result["context"]["wired_inputs"] == [
        {"input_index": 0, "source_path": source.path(), "source_output_index": 0}
    ]


@pytest.mark.parametrize("parameters", [{"missing": 1}, {"size": float("nan")}, {"size": [[1]]}])
def test_failed_authoring_does_not_leave_nodes(parameters):
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_cop_node.py").create_cop_node(network.path(), "blur", parameters=parameters)
    assert not result["success"]
    assert not network.children()


def test_cross_network_input_rejected_before_creation():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    other = geo.createNode("copnet", "other")
    source = other.createNode("file")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_cop_node.py").create_cop_node(network.path(), "blur", input_nodes=[source.path()])
    assert not result["success"]
    assert not network.children()


def test_cached_validation_propagates_read_failures():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    broken = network.createNode("blur")
    broken.error_messages = ["missing input"]
    mod = _load("validate_cop_network.py")
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.validate_cop_network(network.path())
        assert result["success"] and not result["context"]["valid"]
        assert result["context"]["validation_scope"] == "cached_diagnostics"

        def unreadable():
            raise RuntimeError("cannot read errors")

        broken.errors = unreadable
        assert not mod.validate_cop_network(network.path())["success"]


def test_create_cop_node_has_no_dead_skipped_parameters():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_cop_node.py").create_cop_node(network.path(), "blur", parameters={"size": 2})
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"size": 2}
    assert "skipped_parameters" not in result["context"]


def test_create_cop_node_fails_on_unknown_parameter_and_destroys_node():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_cop_node.py").create_cop_node(network.path(), "blur", parameters={"nope": 1})
    assert not result["success"]
    assert network.children() == ()


def test_build_composite_chain_wires_each_step_into_the_previous():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    source = network.createNode("file")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("build_composite_chain.py").build_composite_chain(
            network.path(),
            steps=[
                {"filter_type": "blur", "parameters": {"size": 1}},
                {"filter_type": "composite"},
                {"filter_type": "output", "node_name": "rop_image1"},
            ],
            source_path=source.path(),
        )
    assert result["success"]
    context = result["context"]
    assert context["node_count"] == 3
    # `composite` maps to the Copernicus `blend` node type.
    assert [item["node_type"] for item in context["nodes"]] == ["blur", "blend", "rop_image"]
    assert all(item["wired"] for item in context["nodes"])
    assert context["source_path"] == source.path()
    assert context["setup_state"] == "wired"
    nodes = [hou.node(item["node_path"]) for item in context["nodes"]]
    assert nodes[0].inputs() == (source,)
    assert nodes[1].inputs() == (nodes[0],)
    assert nodes[2].inputs() == (nodes[1],)


def test_build_composite_chain_rolls_back_every_owned_node():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    preserved = network.createNode("file")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("build_composite_chain.py").build_composite_chain(
            network.path(),
            steps=[{"filter_type": "blur"}, {"filter_type": "colorcorrect", "parameters": {"nope": 1}}],
        )
    assert not result["success"]
    assert network.children() == (preserved,)


@pytest.mark.parametrize(
    "steps,message",
    [
        ([], "steps must be a non-empty list"),
        ([{"node_name": "blur1"}], "requires filter_type"),
        ([{"filter_type": "blur"}] * 17, "at most 16"),
    ],
)
def test_build_composite_chain_validates_steps(steps, message):
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("build_composite_chain.py").build_composite_chain(network.path(), steps=steps)
    assert not result["success"]
    assert message in skill_error_detail(result)
    assert network.children() == ()


def test_cook_cop_node_reports_cook_state_and_diagnostics():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    node = network.createNode("blur")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("cook_cop_node.py").cook_cop_node(node.path())
    assert result["success"]
    context = result["context"]
    assert context["cooked"] is True
    assert context["forced"] is True
    assert context["valid"] is True
    assert context["artifact_verified"] is False
    assert node.cooks == [("node", True)]


def test_cook_cop_node_reports_failure_without_raising():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    node = network.createNode("blur")
    node.reject_create = True

    def reject(force=False):
        raise RuntimeError("cook exploded")

    node.cook = reject
    node.error_messages = ["stale error"]
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("cook_cop_node.py").cook_cop_node(node.path())
    assert result["success"]
    assert result["context"]["cooked"] is False
    assert result["context"]["valid"] is False
    assert "stale error" in result["context"]["errors"]
    assert any("cook exploded" in item for item in result["context"]["errors"])


def test_inspect_cop_output_prefers_explicit_path(tmp_path):
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    node = network.createNode("rop_image")
    artifact = tmp_path / "comp.exr"
    artifact.write_bytes(b"0123456789")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_cop_output.py").inspect_cop_output(node.path(), output_path=str(artifact))
    assert result["success"]
    context = result["context"]
    assert context["output_path"] == str(artifact)
    assert context["output_path_source"] == "argument"
    assert context["artifact_exists"] is True
    assert context["artifact_size_bytes"] == 10
    assert context["render_verified"] is False


def test_inspect_cop_output_probes_output_parameters(tmp_path):
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    node = network.createNode("rop_image")
    artifact = tmp_path / "out.png"
    artifact.write_bytes(b"abc")
    node.parms["copoutput"] = type(node.parms["size"])("copoutput", str(artifact))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_cop_output.py").inspect_cop_output(node.path())
    assert result["success"]
    assert result["context"]["output_path_source"] == "copoutput"
    assert result["context"]["artifact_exists"] is True
    assert result["context"]["artifact_size_bytes"] == 3


def test_inspect_cop_output_reports_missing_artifact(tmp_path):
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    node = network.createNode("rop_image")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_cop_output.py").inspect_cop_output(
            node.path(), output_path=str(tmp_path / "never_written.exr")
        )
    assert result["success"]
    assert result["context"]["artifact_exists"] is False
    assert result["context"]["artifact_size_bytes"] is None


def test_inspect_cop_output_reports_unresolved_path():
    root, geo, hou = scene()
    network = geo.createNode("copnet")
    node = network.createNode("rop_image")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_cop_output.py").inspect_cop_output(node.path())
    assert result["success"]
    assert result["context"]["output_path"] is None
    assert result["context"]["output_path_source"] is None
    assert result["context"]["artifact_exists"] is False
