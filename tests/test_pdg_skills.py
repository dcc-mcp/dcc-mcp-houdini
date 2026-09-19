"""Public domain tool contracts with explicit HOM doubles."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from domain_graph_fakes import scene
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-pdg"


def _load(name):
    spec = importlib.util.spec_from_file_location("pdg_" + name[:-3], _ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_create_and_connect_pdg_nodes():
    root, geo, hou = scene()
    network = root.createNode("topnet")
    source = network.createNode("genericgenerator")
    with patch.dict(sys.modules, {"hou": hou}):
        created = _load("create_pdg_node.py").create_pdg_node(
            network.path(), "ropfetch", input_nodes=[source.path()], parameters={"service": "farm"}
        )
        assert created["success"]
        sink = hou.node(created["context"]["node_path"])
        connected = _load("connect_pdg_nodes.py").connect_pdg_nodes(sink.path(), source.path(), input_index=1)
    assert connected["success"]
    assert sink.inputs() == (source, source)


@pytest.mark.parametrize("node_type", ["ropfetch;bad", "../ropfetch", ""])
def test_create_pdg_node_rejects_invalid_type(node_type):
    root, geo, hou = scene()
    network = root.createNode("topnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pdg_node.py").create_pdg_node(network.path(), node_type)
    assert not result["success"] and not network.children()


@pytest.mark.parametrize(
    "states,block,outcome,valid",
    [
        (["CookedSuccess", "CookedCache"], True, "completed", True),
        (["CookedSuccess", "CookedFail"], True, "failed", False),
        (["CookedCancel"], False, "failed", False),
        (["Cooking"], False, "submitted", False),
        (["Waiting"], True, "incomplete", False),
        ([], True, "incomplete", False),
    ],
)
def test_cook_reports_authoritative_item_states(states, block, outcome, valid):
    root, geo, hou = scene()
    network = root.createNode("topnet")
    task = network.createNode("genericgenerator")
    task.pdg_node = SimpleNamespace(workItems=[SimpleNamespace(state=SimpleNamespace(name=s)) for s in states])
    with patch.dict(sys.modules, {"hou": hou}):
        inspected = _load("inspect_pdg_graph.py").inspect_pdg_graph(network.path())
        result = _load("cook_pdg_graph.py").cook_pdg_graph(network.path(), block=block)
    assert inspected["context"]["work_item_count"] == len(states)
    assert result["success"]
    assert result["context"]["outcome"] == outcome
    assert result["context"]["valid"] is valid
    assert network.cooks == [("output", block)]


def test_uninitialized_graph_does_not_claim_completion():
    root, geo, hou = scene()
    task = root.createNode("topnet").createNode("genericgenerator")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("cook_pdg_graph.py").cook_pdg_graph(task.path())
    assert result["success"] and not result["context"]["valid"]
    assert result["context"]["work_item_count"] is None
    assert task.cooks == [("branch", True)]


def test_type_error_does_not_retry_or_drop_block():
    root, geo, hou = scene()
    task = root.createNode("topnet").createNode("genericgenerator")
    calls = []

    def failing(block=False):
        calls.append(block)
        raise TypeError("internal cook error")

    task.cookWorkItems = failing
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("cook_pdg_graph.py").cook_pdg_graph(task.path(), block=False)
    assert not result["success"]
    assert calls == [False]


def test_create_pdg_node_has_no_dead_skipped_parameters():
    """parameter_edit hard-fails, so the payload must not claim a skip path."""
    root, geo, hou = scene()
    network = root.createNode("topnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pdg_node.py").create_pdg_node(network.path(), "ropfetch", parameters={"service": "farm"})
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"service": "farm"}
    assert "skipped_parameters" not in result["context"]


def test_create_pdg_node_fails_and_cleans_up_on_unknown_parameter():
    root, geo, hou = scene()
    network = root.createNode("topnet")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("create_pdg_node.py").create_pdg_node(network.path(), "ropfetch", parameters={"nope": 1})
    assert not result["success"]
    assert network.children() == ()
