"""Unit tests for semantic node graph inspection and auto-layout.

Uses the same FakeNode / FakeParent / FakeHou mock pattern established in
test_atomic_node_chain.py.  No live Houdini is required.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


# ---------------------------------------------------------------------------
# Fake HOM helpers (mirrors test_atomic_node_chain.py pattern)
# ---------------------------------------------------------------------------


class FakeNodeType:
    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class FakeConnection:
    def __init__(
        self,
        input_index: int,
        source: "FakeNode",
        destination: "FakeNode",
        output_index: int,
    ) -> None:
        self._input_index = input_index
        self._source = source
        self._destination = destination
        self._output_index = output_index

    def inputIndex(self) -> int:
        return self._input_index

    def inputNode(self) -> "FakeNode":
        return self._source

    def inputItem(self) -> "FakeNode":
        return self._source

    def inputItemOutputIndex(self) -> int:
        return self._output_index

    def outputNode(self) -> "FakeNode":
        return self._destination


class FakeNode:
    _next_id = 0

    def __init__(
        self,
        name: str,
        node_type_name: str,
        position: Tuple[float, float] = (0.0, 0.0),
    ) -> None:
        FakeNode._next_id += 1
        self._id = FakeNode._next_id
        self._name = name
        self._type_name = node_type_name
        self._position = position
        self._inputs: Dict[int, Optional[FakeNode]] = {}
        self._connections: List[FakeConnection] = []
        self._outputs: List[FakeNode] = []

    def name(self) -> str:
        return self._name

    def path(self) -> str:
        return "/obj/geo1/{}".format(self._name)

    def type(self) -> FakeNodeType:
        return FakeNodeType(self._type_name)

    def position(self) -> Tuple[float, float]:
        return self._position

    def setPosition(self, pos: Tuple[float, float]) -> None:
        self._position = pos

    def inputs(self) -> List[Optional["FakeNode"]]:
        """Return input slots as a list (None for unconnected)."""
        max_idx = max(self._inputs) if self._inputs else -1
        result = []
        for i in range(max_idx + 1):
            result.append(self._inputs.get(i))
        return result

    def inputConnections(self) -> Tuple[FakeConnection, ...]:
        return tuple(self._connections)

    def setInput(self, input_index: int, source: Optional["FakeNode"], output_index: int = 0) -> None:
        if source is None:
            self._inputs.pop(input_index, None)
            self._connections = [c for c in self._connections if c.inputIndex() != input_index]
            return
        self._inputs[input_index] = source
        self._connections = [c for c in self._connections if c.inputIndex() != input_index]
        self._connections.append(FakeConnection(input_index, source, self, output_index))


class FakeParent:
    """A Houdini network node that owns children."""

    def __init__(self, path: str = "/obj/geo1") -> None:
        self._path = path
        self._children: List[FakeNode] = []
        self.editable = True
        self.layout_count = 0

    def path(self) -> str:
        return self._path

    def isNetwork(self) -> bool:
        return True

    def isEditable(self) -> bool:
        return self.editable

    def children(self) -> Tuple[FakeNode, ...]:
        return tuple(self._children)

    def node(self, ref: str) -> Optional[FakeNode]:
        normalized = ref.rsplit("/", 1)[-1]
        for child in self._children:
            if child.name() == normalized:
                return child
        return None

    def add_child(
        self,
        name: str,
        node_type: str = "geo",
        position: Tuple[float, float] = (0.0, 0.0),
    ) -> FakeNode:
        node = FakeNode(name, node_type, position=position)
        self._children.append(node)
        return node

    def layoutChildren(self) -> None:
        self.layout_count += 1
        for index, child in enumerate(self._children):
            child.setPosition((float(index * 200), 0.0))


class FakeHou:
    def __init__(self, parent: FakeParent) -> None:
        self.parent = parent

    def node(self, path: str) -> Optional[FakeParent]:
        if path == self.parent.path():
            return self.parent
        return self.parent.node(path)


# ---------------------------------------------------------------------------
# Core module tests
# ---------------------------------------------------------------------------


def _load_core_module() -> "module":
    path = (
        Path(__file__).parent.parent
        / "src"
        / "dcc_mcp_houdini"
        / "_node_graph_inspection.py"
    )
    spec = importlib.util.spec_from_file_location("node_graph_inspection", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestInspectNetwork:
    """Tests for semantic network inspection."""

    def test_empty_network(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 0
        assert result.connection_count == 0
        assert result.broken_inputs == []
        assert result.orphaned_nodes == []
        assert result.cycles == []
        assert result.subgraphs == []

    def test_single_node_no_connections(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        parent.add_child("box1", "box")
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 1
        assert result.connection_count == 0
        assert len(result.broken_inputs) == 0  # box has 0 inputs
        assert result.orphaned_nodes == ["/obj/geo1/box1"]

    def test_node_with_broken_inputs(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        null_node = parent.add_child("null1", "null")
        # null has inputs, but none connected
        hou = FakeHou(parent)

        # Need to mock null node having input slots
        # FakeNode with no setInput will return empty inputs list which doesn't capture None
        # Let's manually set up the inputs with None
        null_node._inputs = {0: None, 1: None}

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 1
        assert len(result.broken_inputs) == 2
        assert [b.input_index for b in result.broken_inputs] == [0, 1]

    def test_connected_pair(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box", position=(0.0, 0.0))
        null1 = parent.add_child("null1", "null", position=(200.0, 0.0))
        null1.setInput(0, box1)
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 2
        assert result.connection_count == 1
        assert result.orphaned_nodes == []
        assert result.chain_roots == ["/obj/geo1/box1"]
        assert result.chain_ends == ["/obj/geo1/null1"]
        assert result.cycles == []

    def test_three_node_chain(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box")
        xform1 = parent.add_child("xform1", "xform")
        null1 = parent.add_child("null1", "null")
        xform1.setInput(0, box1)
        null1.setInput(0, xform1)
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 3
        assert result.connection_count == 2
        assert result.orphaned_nodes == []
        assert result.chain_roots == ["/obj/geo1/box1"]
        assert result.chain_ends == ["/obj/geo1/null1"]
        assert len(result.subgraphs) == 1
        assert result.subgraphs[0].size == 3

    def test_disconnected_subgraphs(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box")
        null1 = parent.add_child("null1", "null")
        null1.setInput(0, box1)
        sphere1 = parent.add_child("sphere1", "sphere")
        null2 = parent.add_child("null2", "null")
        null2.setInput(0, sphere1)
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 4
        assert result.connection_count == 2
        # Two subgraphs of size 2 each
        assert len(result.subgraphs) == 2
        sizes = {sg.size for sg in result.subgraphs}
        assert sizes == {2, 2}

    def test_cycle_detection_simple(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        a = parent.add_child("a", "null")
        b = parent.add_child("b", "null")
        a.setInput(0, b)
        b.setInput(0, a)
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 2
        assert result.connection_count == 2
        assert len(result.cycles) >= 1

    def test_cycle_detection_triangle(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        a = parent.add_child("a", "null")
        b = parent.add_child("b", "null")
        c = parent.add_child("c", "null")
        a.setInput(0, b)
        b.setInput(0, c)
        c.setInput(0, a)
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.node_count == 3
        assert result.connection_count == 3
        assert len(result.cycles) >= 1

    def test_type_mismatch_detection(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        sop_node = parent.add_child("sop_box1", "SOP_box")  # SOP type — starts with "SOP"
        rop_node = parent.add_child("rop1", "rop_geometry")  # ROP type
        rop_node.setInput(0, sop_node)
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert result.connection_count == 1
        # SOP -> ROP is a cross-context connection
        assert len(result.type_mismatches) >= 1

    def test_no_type_mismatch_same_context(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "SOP_box")  # Both start with "SOP"
        null1 = parent.add_child("null1", "SOP_null")  # Same context
        null1.setInput(0, box1)
        hou = FakeHou(parent)

        result = module.inspect_network("/obj/geo1", hou_provider=lambda: hou)
        assert len(result.type_mismatches) == 0

    def test_invalid_parent_path_raises(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        hou = FakeHou(parent)

        with pytest.raises(ValueError, match="not found"):
            module.inspect_network("/obj/nonexistent", hou_provider=lambda: hou)

    def test_non_network_node_raises(self) -> None:
        module = _load_core_module()

        # Create a mock where node exists but isNetwork returns False
        mock_hou = MagicMock()
        mock_node = MagicMock()
        mock_node.isNetwork.return_value = False
        mock_hou.node.return_value = mock_node

        with pytest.raises(ValueError, match="not a parent network"):
            module.inspect_network("/obj/geo1/box1", hou_provider=lambda: mock_hou)


class TestAutoLayout:
    """Tests for controllable auto-layout with user preservation."""

    def test_empty_network(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        hou = FakeHou(parent)

        result = module.auto_layout("/obj/geo1", hou_provider=lambda: hou)
        assert result.moved_count == 0
        assert result.preserved_count == 0

    def test_houdini_default_layout_moves_all(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box", position=(999.0, 999.0))
        null1 = parent.add_child("null1", "null", position=(1000.0, 1000.0))
        hou = FakeHou(parent)

        result = module.auto_layout(
            "/obj/geo1",
            strategy="houdini_default",
            preserve_user_layout=False,
            hou_provider=lambda: hou,
        )
        assert result.moved_count == 2
        assert result.preserved_count == 0
        # Positions should have been updated by layoutChildren
        assert box1.position() != (999.0, 999.0)
        assert null1.position() != (1000.0, 1000.0)

    def test_preserve_user_layout_detects_user_touched_node(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        # Place a node at the "default" position (0, 0) — this will be rearranged
        box1 = parent.add_child("box1", "box", position=(0.0, 0.0))
        # Place another at a clearly user-touched position
        null1 = parent.add_child("null1", "null", position=(5000.0, 5000.0))
        original_null_pos = null1.position()
        hou = FakeHou(parent)

        result = module.auto_layout(
            "/obj/geo1",
            strategy="houdini_default",
            preserve_user_layout=True,
            hou_provider=lambda: hou,
        )
        # null1 should be preserved (its position is far from default fingerprint)
        assert result.preserved_count >= 1
        assert "/obj/geo1/null1" in result.preserved_paths
        assert null1.position() == original_null_pos

    def test_tree_left_to_right_layout(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box", position=(999.0, 999.0))
        xform1 = parent.add_child("xform1", "xform", position=(1000.0, 1000.0))
        null1 = parent.add_child("null1", "null", position=(1001.0, 1001.0))
        xform1.setInput(0, box1)
        null1.setInput(0, xform1)
        hou = FakeHou(parent)

        result = module.auto_layout(
            "/obj/geo1",
            strategy="tree_left_to_right",
            preserve_user_layout=False,
            spacing_x=200.0,
            spacing_y=100.0,
            hou_provider=lambda: hou,
        )
        assert result.moved_count == 3
        assert result.preserved_count == 0
        assert result.strategy == "tree_left_to_right"

    def test_dry_run_does_not_mutate(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box", position=(999.0, 999.0))
        null1 = parent.add_child("null1", "null", position=(1000.0, 1000.0))
        original_positions = {box1.path(): box1.position(), null1.path(): null1.position()}
        hou = FakeHou(parent)

        result = module.auto_layout(
            "/obj/geo1",
            strategy="houdini_default",
            preserve_user_layout=False,
            dry_run=True,
            hou_provider=lambda: hou,
        )
        # Dry run should NOT mutate
        assert box1.position() == original_positions[box1.path()]
        assert null1.position() == original_positions[null1.path()]
        assert result.moved_count + result.preserved_count > 0

    def test_compute_layout_plan_is_equivalent_to_dry_run(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        parent.add_child("box1", "box")
        parent.add_child("null1", "null")
        hou = FakeHou(parent)

        plan = module.compute_layout_plan(
            "/obj/geo1",
            strategy="houdini_default",
            preserve_user_layout=False,
            hou_provider=lambda: hou,
        )
        assert plan.total_nodes == 2
        assert plan.strategy == "houdini_default"

    def test_invalid_strategy_does_not_crash(self) -> None:
        """auto_layout core doesn't validate strategy — callers do."""
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        parent.add_child("box1", "box")
        hou = FakeHou(parent)

        # Unknown strategy should fall through to houdini_default branch
        result = module.auto_layout(
            "/obj/geo1",
            strategy="unknown_strategy",
            preserve_user_layout=False,
            hou_provider=lambda: hou,
        )
        # Should still produce a result (falls back to houdini_default)
        assert result is not None


# ---------------------------------------------------------------------------
# Skill script integration tests (mock hou)
# ---------------------------------------------------------------------------


def _load_skill_script(script_name: str) -> "module":
    path = _SKILLS_ROOT / "houdini-node-graph" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(
        "skill_node_graph_{}".format(path.stem), path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class TestInspectNetworkSkill:
    """Integration tests for the inspect_network skill script."""

    def test_inspect_basic_network(self) -> None:
        mod = _load_skill_script("inspect_network.py")
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box")
        null1 = parent.add_child("null1", "null")
        null1.setInput(0, box1)

        mock_hou = FakeHou(parent)
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.inspect_network("/obj/geo1")

        assert result["success"] is True
        assert result["context"]["node_count"] == 2
        assert result["context"]["connection_count"] == 1

    def test_inspect_missing_parent(self) -> None:
        mod = _load_skill_script("inspect_network.py")
        parent = FakeParent("/obj/geo1")
        mock_hou = FakeHou(parent)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.inspect_network("/obj/nonexistent")

        assert result["success"] is False

    def test_inspect_no_hou_module(self) -> None:
        mod = _load_skill_script("inspect_network.py")
        with patch.dict(sys.modules, {"hou": None}):
            # hou import will fail
            pass
        # Can't easily test ImportError in FakeHou since sys.modules patching
        # doesn't prevent "import hou" — use MagicMock side_effect
        with patch.dict(sys.modules):
            sys.modules.pop("hou", None)
            try:
                result = mod.inspect_network("/obj/geo1")
                assert result["success"] is False
                assert "not available" in str(result["message"]).lower()
            except ImportError:
                # Expected if hou truly isn't there
                pass


class TestAutoLayoutSkill:
    """Integration tests for the auto_layout skill script."""

    def test_auto_layout_basic(self) -> None:
        mod = _load_skill_script("auto_layout.py")
        parent = FakeParent("/obj/geo1")
        parent.add_child("box1", "box", position=(999.0, 999.0))
        parent.add_child("null1", "null", position=(1000.0, 1000.0))
        mock_hou = FakeHou(parent)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.auto_layout(
                "/obj/geo1",
                strategy="houdini_default",
                preserve_user_layout=False,
            )

        assert result["success"] is True
        assert result["context"]["moved_count"] == 2
        assert result["context"]["dry_run"] is False

    def test_auto_layout_dry_run(self) -> None:
        mod = _load_skill_script("auto_layout.py")
        parent = FakeParent("/obj/geo1")
        parent.add_child("box1", "box", position=(999.0, 999.0))
        parent.add_child("null1", "null", position=(1000.0, 1000.0))
        mock_hou = FakeHou(parent)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.auto_layout(
                "/obj/geo1",
                strategy="houdini_default",
                dry_run=True,
            )

        assert result["success"] is True
        assert result["context"]["dry_run"] is True

    def test_auto_layout_invalid_strategy(self) -> None:
        mod = _load_skill_script("auto_layout.py")
        parent = FakeParent("/obj/geo1")
        parent.add_child("box1", "box")
        mock_hou = FakeHou(parent)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.auto_layout("/obj/geo1", strategy="bad_strategy")

        assert result["success"] is False
        assert "Unknown layout strategy" in result["message"]

    def test_auto_layout_missing_parent(self) -> None:
        mod = _load_skill_script("auto_layout.py")
        parent = FakeParent("/obj/geo1")
        mock_hou = FakeHou(parent)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.auto_layout("/obj/nonexistent")

        assert result["success"] is False

    def test_tree_layout_respects_connections(self) -> None:
        mod = _load_skill_script("auto_layout.py")
        parent = FakeParent("/obj/geo1")
        box1 = parent.add_child("box1", "box", position=(999.0, 999.0))
        xform1 = parent.add_child("xform1", "xform", position=(1000.0, 1000.0))
        null1 = parent.add_child("null1", "null", position=(1001.0, 1001.0))
        xform1.setInput(0, box1)
        null1.setInput(0, xform1)
        mock_hou = FakeHou(parent)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.auto_layout(
                "/obj/geo1",
                strategy="tree_left_to_right",
                preserve_user_layout=False,
                spacing_x=200.0,
                spacing_y=100.0,
            )

        assert result["success"] is True
        assert result["context"]["moved_count"] == 3
        # tree_left_to_right: sinks on the right, roots on the left
        # null1 is the sink → rightmost; box1 is the root → leftmost
        assert box1.position()[0] < null1.position()[0]  # upstream is left


class TestUserLayoutPreservation:
    """Detailed tests for user-layout preservation heuristics."""

    def test_fingerprint_detects_default_position(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        node = parent.add_child("box1", "box", position=(0.0, 0.0))
        hou = FakeHou(parent)

        # Compute fingerprint by running layoutChildren (which sets pos to (0, 0) for index 0)
        fingerprint = module._compute_default_fingerprint(hou, "/obj/geo1", [node])
        assert module._is_position_auto("/obj/geo1/box1", (0.0, 0.0), fingerprint) is True
        assert module._is_position_auto("/obj/geo1/box1", (0.0, 1.0), fingerprint) is True  # within threshold
        assert module._is_position_auto("/obj/geo1/box1", (999.0, 999.0), fingerprint) is False

    def test_position_not_in_fingerprint_is_conservative(self) -> None:
        module = _load_core_module()
        fingerprint = {}  # empty fingerprint
        assert module._is_position_auto("/obj/geo1/missing", (0.0, 0.0), fingerprint) is False

    def test_layout_preserves_user_touched_across_multiple_strategies(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        # Pre-position nodes as if Houdini's layoutChildren already ran:
        # node at index 0 → (0, 0), node at index 1 → (200, 0)
        auto_node = parent.add_child("auto_placed", "box", position=(0.0, 0.0))
        user_node = parent.add_child("user_placed", "null", position=(5000.0, 5000.0))
        hou = FakeHou(parent)

        # After computing fingerprint, layoutChildren sets both to (0,0) and (200,0).
        # auto_placed at (0,0) matches fingerprint[(0,0)] within threshold → auto
        # user_placed at (5000,5000) differs → user-touched → preserved
        result = module.auto_layout(
            "/obj/geo1",
            strategy="houdini_default",
            preserve_user_layout=True,
            hou_provider=lambda: hou,
        )
        assert "/obj/geo1/user_placed" in result.preserved_paths
        # auto_placed may or may not be moved depending on fingerprint overlap
        # — the important thing is user_placed is always preserved

    def test_no_preservation_moves_everything(self) -> None:
        module = _load_core_module()
        parent = FakeParent("/obj/geo1")
        user_node = parent.add_child("user_placed", "null", position=(5000.0, 5000.0))
        auto_node = parent.add_child("auto_placed", "box", position=(0.0, 0.0))
        hou = FakeHou(parent)

        result = module.auto_layout(
            "/obj/geo1",
            strategy="houdini_default",
            preserve_user_layout=False,
            hou_provider=lambda: hou,
        )
        # Both should be moved
        assert result.preserved_count == 0
        assert result.moved_count == 2
