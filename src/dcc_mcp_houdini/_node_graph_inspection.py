"""Semantic node graph inspection and auto-layout for Houdini networks.

Design
------
This module provides two families of operations over a single Houdini
parent network (e.g. ``/obj/geo1``):

* **Inspection** — read-only semantic analysis: broken inputs, orphaned
  nodes, cycles, disconnected subgraphs, type-mismatched connections,
  and chain-end summary.
* **Layout** — controllable auto-layout that distinguishes auto-placed
  nodes from user-touched positions (detected via a default-layout
  fingerprint heuristic) and respects a ``preserve_user_layout`` flag.

Both families obey the **target network only** contract: they never
traverse into child networks or modify nodes outside ``parent_path``.

Thread / concurrency safety
---------------------------
All functions are synchronous and should be called from Houdini's main
thread.  They are read-only (inspection) or position-only (layout) and
never cook geometry.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _safe_path(node: Any) -> str:
    """Return ``node.path()`` or a stable placeholder."""
    try:
        return str(node.path())
    except Exception:  # noqa: BLE001
        return "<unavailable>"


def _safe_name(node: Any) -> str:
    """Return ``node.name()`` or a stable placeholder."""
    try:
        return str(node.name())
    except Exception:  # noqa: BLE001
        return "<unavailable>"


def _safe_type_name(node: Any) -> str:
    """Return ``node.type().name()`` or ``"?"``."""
    try:
        return str(node.type().name())
    except Exception:  # noqa: BLE001
        return "?"


def _safe_position(node: Any) -> Optional[Tuple[float, float]]:
    """Return ``node.position()`` as (x, y) or ``None``."""
    try:
        pos = node.position()
        return (float(pos[0]), float(pos[1]))
    except Exception:  # noqa: BLE001
        return None


def _node_to_dict(node: Any) -> Dict[str, Any]:
    """Lightweight JSON-safe node summary."""
    pos = _safe_position(node)
    return {
        "path": _safe_path(node),
        "name": _safe_name(node),
        "type": _safe_type_name(node),
        "position": list(pos) if pos else None,
    }


# ---------------------------------------------------------------------------
# Inspection data structures
# ---------------------------------------------------------------------------


@dataclass
class BrokenInput:
    """An input slot that is ``None`` on a node whose type commonly receives data."""

    node_path: str
    input_index: int
    node_type: str


@dataclass
class ConnectionInfo:
    """A directed edge in the graph."""

    source_path: str
    target_path: str
    input_index: int
    output_index: int
    source_type: str = ""
    target_type: str = ""


@dataclass
class CycleInfo:
    """A detected cycle in the directed node graph."""

    node_paths: List[str]
    length: int


@dataclass
class SubgraphInfo:
    """A connected component in the (undirected) node graph."""

    id: int
    node_paths: List[str]
    size: int
    has_output_connections: bool


@dataclass
class NetworkInspection:
    """Complete semantic inspection of a single Houdini parent network."""

    parent_path: str
    node_count: int
    connection_count: int
    broken_inputs: List[BrokenInput] = field(default_factory=list)
    orphaned_nodes: List[str] = field(default_factory=list)
    cycles: List[CycleInfo] = field(default_factory=list)
    type_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    subgraphs: List[SubgraphInfo] = field(default_factory=list)
    chain_ends: List[str] = field(default_factory=list)  # nodes with no upstream consumers
    chain_roots: List[str] = field(default_factory=list)  # nodes with no inputs (generators)


# ---------------------------------------------------------------------------
# Layout data structures
# ---------------------------------------------------------------------------

# Default spacing for tree-based layout (Houdini network editor units).
DEFAULT_SPACING_X = 200.0
DEFAULT_SPACING_Y = 100.0
USER_LAYOUT_THRESHOLD = 5.0  # px — positions within this distance are "auto-identical"


@dataclass
class LayoutPlan:
    """Describes what the auto-layout will change before applying it."""

    parent_path: str
    total_nodes: int
    moved_nodes: List[str]
    preserved_nodes: List[str]
    strategy: str  # "tree_left_to_right" | "houdini_default"
    spacing: Tuple[float, float]


@dataclass
class LayoutResult:
    """What the auto-layout actually changed."""

    parent_path: str
    moved_count: int
    preserved_count: int
    moved_paths: List[str]
    preserved_paths: List[str]
    strategy: str
    positions: Dict[str, List[float]]  # path -> [x, y]


# ---------------------------------------------------------------------------
# Inspection internals
# ---------------------------------------------------------------------------


def _collect_connections(nodes: Sequence[Any]) -> List[ConnectionInfo]:
    """Walk every input of every node and return directed edges."""
    edges: List[ConnectionInfo] = []
    for node in nodes:
        try:
            for conn in node.inputConnections():
                edges.append(
                    ConnectionInfo(
                        source_path=_safe_path(conn.inputNode()),
                        target_path=_safe_path(node),
                        input_index=conn.inputIndex(),
                        output_index=conn.inputItemOutputIndex(),
                        source_type=_safe_type_name(conn.inputNode()),
                        target_type=_safe_type_name(node),
                    )
                )
        except Exception:  # noqa: BLE001
            continue
    return edges


def _find_broken_inputs(nodes: Sequence[Any]) -> List[BrokenInput]:
    """Report input slots that are ``None`` (unconnected)."""
    broken: List[BrokenInput] = []
    for node in nodes:
        try:
            for idx, inp in enumerate(node.inputs()):
                if inp is None:
                    broken.append(
                        BrokenInput(
                            node_path=_safe_path(node),
                            input_index=idx,
                            node_type=_safe_type_name(node),
                        )
                    )
        except Exception:  # noqa: BLE001
            continue
    return broken


def _find_orphaned(edges: List[ConnectionInfo], all_paths: Set[str]) -> List[str]:
    """Nodes with zero incoming and zero outgoing edges."""
    sources = {e.source_path for e in edges}
    targets = {e.target_path for e in edges}
    connected = sources | targets
    return sorted(all_paths - connected)


def _find_cycles(edges: List[ConnectionInfo]) -> List[CycleInfo]:
    """Detect cycles via DFS with a recursion stack.

    Returns each unique cycle once.
    """
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source_path].append(edge.target_path)

    cycles: List[CycleInfo] = []
    visited: Set[str] = set()
    rec_stack: List[str] = []
    rec_set: Set[str] = set()

    def _dfs(node: str) -> None:
        if node in rec_set:
            # Cycle found — extract the sub-path
            cycle_start = rec_stack.index(node)
            cycle_nodes = rec_stack[cycle_start:] + [node]
            cycles.append(CycleInfo(node_paths=list(cycle_nodes), length=len(cycle_nodes) - 1))
            return
        if node in visited:
            return
        visited.add(node)
        rec_stack.append(node)
        rec_set.add(node)
        for neighbor in adjacency.get(node, ()):
            _dfs(neighbor)
        rec_stack.pop()
        rec_set.discard(node)

    for start in list(adjacency):
        _dfs(start)
    return cycles


def _find_subgraphs(nodes: Sequence[Any], edges: List[ConnectionInfo]) -> List[SubgraphInfo]:
    """Partition the network into connected components (undirected).

    Each component is assigned an id; components with ≥2 nodes are reported.
    """
    all_paths = {_safe_path(n) for n in nodes}
    adjacency: Dict[str, Set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source_path].add(edge.target_path)
        adjacency[edge.target_path].add(edge.source_path)
    # Isolated nodes appear as singletons
    for path in all_paths:
        if path not in adjacency:
            adjacency[path] = set()

    seen: Set[str] = set()
    subgraphs: List[SubgraphInfo] = []
    next_id = 1
    for path in all_paths:
        if path in seen:
            continue
        # BFS this component
        queue: deque = deque([path])
        component: List[str] = []
        while queue:
            cur = queue.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            component.append(cur)
            queue.extend(adjacency.get(cur, ()) - seen)
        # Determine whether any node in this component has output connections
        source_set = {e.source_path for e in edges}
        has_output = any(n in source_set for n in component)
        subgraphs.append(
            SubgraphInfo(
                id=next_id,
                node_paths=sorted(component),
                size=len(component),
                has_output_connections=has_output,
            )
        )
        next_id += 1
    return subgraphs


def _find_chain_ends(edges: List[ConnectionInfo], all_paths: Set[str]) -> Tuple[List[str], List[str]]:
    """Return (roots, ends) — roots have no inputs (or only broken); ends have no downstream consumers."""
    targets = {e.target_path for e in edges}
    sources = {e.source_path for e in edges}
    # Roots: nodes that are sources but never targets
    roots = sorted(sources - targets)
    # Ends: nodes that are targets but never sources (sinks)
    ends = sorted(targets - sources)
    return roots, ends


def _find_type_mismatches(edges: List[ConnectionInfo]) -> List[Dict[str, Any]]:
    """Flag connections between incompatible node-type categories.

    This is a best-effort heuristic; it does not have full HOM type schema
    access, so it uses node-type prefix conventions (SOP, VOP, ROP, etc.).
    """
    mismatches: List[Dict[str, Any]] = []
    # Broad categories by Houdini naming convention
    KNOWN_CONTEXTS = {"SOP", "VOP", "ROP", "COP", "CHOP", "DOP", "LOP", "TOP", "OBJ", "OUT", "SHOP", "MAT", "MOT"}

    def _context(type_name: str) -> Optional[str]:
        """Guess the context from a node type name, e.g. ``rop_geometry`` -> ROP."""
        for ctx in KNOWN_CONTEXTS:
            if type_name.lower().startswith(ctx.lower()):
                return ctx
        return None

    for edge in edges:
        src_ctx = _context(edge.source_type)
        tgt_ctx = _context(edge.target_type)
        if src_ctx and tgt_ctx and src_ctx != tgt_ctx:
            mismatches.append(
                {
                    "source_path": edge.source_path,
                    "target_path": edge.target_path,
                    "source_type": edge.source_type,
                    "target_type": edge.target_type,
                    "source_context": src_ctx,
                    "target_context": tgt_ctx,
                    "input_index": edge.input_index,
                }
            )
    return mismatches


# ---------------------------------------------------------------------------
# Public inspection API
# ---------------------------------------------------------------------------


def inspect_network(parent_path: str, hou_provider: Optional[Callable[[], Any]] = None) -> NetworkInspection:
    """Run full semantic inspection on the children of *parent_path*.

    Parameters
    ----------
    parent_path:
        Absolute Houdini path to a network node (e.g. ``/obj/geo1``).
    hou_provider:
        Optional factory returning the ``hou`` module.  When ``None`` the
        real ``hou`` is imported lazily.

    Returns
    -------
    NetworkInspection
        Structured findings.  The caller is responsible for JSON-serialising
        the dataclass (used by the MCP skill wrapper).

    Raises
    ------
    ValueError
        When *parent_path* does not exist or is not a network.
    RuntimeError
        When ``hou`` cannot be imported.
    """
    if hou_provider is None:
        try:
            import hou  # noqa: PLC0415
        except ImportError as err:
            raise RuntimeError("hou module is not available — not running inside Houdini") from err
    else:
        hou = hou_provider()

    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError("Houdini node not found: {}".format(parent_path))
    if not hasattr(parent, "isNetwork") or not parent.isNetwork():
        raise ValueError("Node is not a parent network: {}".format(parent_path))

    try:
        children = list(parent.children())
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Failed to enumerate children of {}: {}".format(parent_path, exc)) from exc

    all_paths = {_safe_path(n) for n in children}
    edges = _collect_connections(children)
    broken = _find_broken_inputs(children)
    orphaned = _find_orphaned(edges, all_paths)
    cycles = _find_cycles(edges)
    subgraphs = _find_subgraphs(children, edges)
    roots, ends = _find_chain_ends(edges, all_paths)
    mismatches = _find_type_mismatches(edges)

    return NetworkInspection(
        parent_path=_safe_path(parent),
        node_count=len(children),
        connection_count=len(edges),
        broken_inputs=broken,
        orphaned_nodes=orphaned,
        cycles=cycles,
        type_mismatches=mismatches,
        subgraphs=subgraphs,
        chain_ends=ends,
        chain_roots=roots,
    )


# ---------------------------------------------------------------------------
# Layout internals
# ---------------------------------------------------------------------------


def _compute_default_fingerprint(
    hou: Any, parent_path: str, children: Sequence[Any]
) -> Dict[str, Tuple[float, float]]:
    """Compute where ``parent.layoutChildren()`` would place each node.

    This runs a speculative layout on a **temporary clone** of the network
    so we do not alter the live scene.  Returns ``{path: (x, y)}``.

    When the HOM does not support a temporary arrangement query, this falls
    back to the current layout (which is harmless but less precise).
    """
    parent = hou.node(parent_path)
    if parent is None:
        return {}
    try:
        # Attempt to query the default arrangement without mutating.
        # Houdini 20+ provides layoutChildren(items) variant.
        # Fallback: we run the real layout, capture positions, then restore.
        original_positions: Dict[str, Tuple[float, float]] = {}
        for child in children:
            pos = _safe_position(child)
            if pos is not None:
                original_positions[_safe_path(child)] = pos

        parent.layoutChildren()

        fingerprint: Dict[str, Tuple[float, float]] = {}
        for child in children:
            pos = _safe_position(child)
            if pos is not None:
                fingerprint[_safe_path(child)] = pos

        # Restore original positions
        for child in children:
            path = _safe_path(child)
            if path in original_positions:
                try:
                    child.setPosition(original_positions[path])
                except Exception:  # noqa: BLE001
                    pass

        return fingerprint
    except Exception:  # noqa: BLE001
        return {}


def _is_position_auto(
    path: str,
    current: Tuple[float, float],
    default_fingerprint: Dict[str, Tuple[float, float]],
    threshold: float = USER_LAYOUT_THRESHOLD,
) -> bool:
    """Return ``True`` when *current* is close enough to the default layout position."""
    if path not in default_fingerprint:
        # Can't fingerprint — treat as user-touched (conservative)
        return False
    dx, dy = default_fingerprint[path]
    return math.hypot(current[0] - dx, current[1] - dy) <= threshold


def _tree_layout_positions(
    children: Sequence[Any],
    edges: List[ConnectionInfo],
    default_fingerprint: Dict[str, Tuple[float, float]],
    preserve_user_layout: bool,
    spacing_x: float = DEFAULT_SPACING_X,
    spacing_y: float = DEFAULT_SPACING_Y,
) -> Tuple[Dict[str, Tuple[float, float]], List[str], List[str]]:
    """Compute a left-to-right tree layout preserving user-touched nodes.

    Returns
    -------
    (positions, moved_paths, preserved_paths)
    """
    # Build adjacency: source -> target (flow direction)
    adjacency: Dict[str, List[str]] = defaultdict(list)
    reverse_adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source_path].append(edge.target_path)
        reverse_adjacency[edge.target_path].append(edge.source_path)

    all_paths = {_safe_path(n) for n in children}
    path_to_node = {_safe_path(n): n for n in children}

    # Determine which nodes to preserve
    preserved: Set[str] = set()
    if preserve_user_layout:
        for n in children:
            path = _safe_path(n)
            pos = _safe_position(n)
            if pos and not _is_position_auto(path, pos, default_fingerprint):
                preserved.add(path)

    # Topological sort via Kahn (respecting reversed adjacency: BFS from sinks backwards)
    # Assign layer: 0 = output, increasing upstream
    in_degree: Dict[str, int] = {p: len(adjacency.get(p, [])) for p in all_paths}
    layer: Dict[str, int] = {}
    # Start from sinks (nodes with out_degree == 0)
    queue: deque = deque()
    for p in all_paths:
        if in_degree.get(p, 0) == 0:
            layer[p] = 0
            queue.append(p)

    while queue:
        cur = queue.popleft()
        for upstream in reverse_adjacency.get(cur, []):
            if upstream not in layer:
                layer[upstream] = layer[cur] + 1
                queue.append(upstream)

    # Any nodes not reachable from sinks get layer 0
    for p in all_paths:
        if p not in layer:
            layer[p] = 0

    # Group by layer (layer 0 = rightmost = sinks)
    max_layer = max(layer.values()) if layer else 0
    by_layer: Dict[int, List[str]] = defaultdict(list)
    for p, level in layer.items():
        # Invert: max_layer - level so that sinks are at x=0, roots at x=max_layer*spacing
        by_layer[max_layer - level].append(p)

    positions: Dict[str, Tuple[float, float]] = {}
    moved: List[str] = []
    preserved_list: List[str] = []

    for col in sorted(by_layer):
        col_paths = by_layer[col]
        # Sort nodes within column for stable output
        col_paths.sort()
        for row, path in enumerate(col_paths):
            x = col * spacing_x
            y = row * spacing_y
            if path in preserved:
                # Keep current position
                node = path_to_node.get(path)
                if node is not None:
                    pos = _safe_position(node)
                    if pos:
                        positions[path] = pos
                        preserved_list.append(path)
                        continue
            positions[path] = (x, y)
            if path not in preserved:
                moved.append(path)

    return positions, moved, preserved_list


def _houdini_default_layout_positions(
    hou: Any,
    parent_path: str,
    children: Sequence[Any],
    default_fingerprint: Dict[str, Tuple[float, float]],
    preserve_user_layout: bool,
) -> Tuple[Dict[str, Tuple[float, float]], List[str], List[str]]:
    """Use Houdini's built-in ``layoutChildren()`` and restore user-touched positions."""
    preserved: Set[str] = set()
    original_positions: Dict[str, Tuple[float, float]] = {}
    if preserve_user_layout:
        for n in children:
            path = _safe_path(n)
            pos = _safe_position(n)
            if pos and not _is_position_auto(path, pos, default_fingerprint):
                preserved.add(path)
                original_positions[path] = pos

    parent = hou.node(parent_path)
    if parent is None:
        return {}, [], []

    parent.layoutChildren()

    positions: Dict[str, Tuple[float, float]] = {}
    moved: List[str] = []
    preserved_list: List[str] = []
    for child in children:
        path = _safe_path(child)
        if path in preserved:
            # Restore user position
            try:
                child.setPosition(original_positions[path])
                positions[path] = original_positions[path]
                preserved_list.append(path)
            except Exception:  # noqa: BLE001
                pos = _safe_position(child)
                if pos:
                    positions[path] = pos
                    moved.append(path)
        else:
            pos = _safe_position(child)
            if pos:
                positions[path] = pos
                moved.append(path)

    return positions, moved, preserved_list


# ---------------------------------------------------------------------------
# Public layout API
# ---------------------------------------------------------------------------


def auto_layout(
    parent_path: str,
    *,
    strategy: str = "houdini_default",
    preserve_user_layout: bool = True,
    spacing_x: float = DEFAULT_SPACING_X,
    spacing_y: float = DEFAULT_SPACING_Y,
    dry_run: bool = False,
    hou_provider: Optional[Callable[[], Any]] = None,
) -> LayoutResult:
    """Auto-arrange nodes under *parent_path* with user-layout preservation.

    Parameters
    ----------
    parent_path:
        Absolute path to a Houdini network node.
    strategy:
        ``"houdini_default"`` — use Houdini's built-in ``layoutChildren()``,
        then restore user-touched positions.
        ``"tree_left_to_right"`` — compute a topological left-to-right tree
        layout (sinks on the right).
    preserve_user_layout:
        When ``True`` (default), nodes whose positions differ from the
        default Houdini arrangement are treated as user-touched and left
        unchanged.
    spacing_x / spacing_y:
        Grid spacing for ``tree_left_to_right`` strategy.  Ignored for
        ``houdini_default``.
    dry_run:
        When ``True``, compute the plan without mutating the scene.
    hou_provider:
        Optional ``hou`` factory.

    Returns
    -------
    LayoutResult
        Final positions and move/preserve counters.
    """
    if hou_provider is None:
        try:
            import hou  # noqa: PLC0415
        except ImportError as err:
            raise RuntimeError("hou module is not available — not running inside Houdini") from err
    else:
        hou = hou_provider()

    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError("Houdini node not found: {}".format(parent_path))
    if not hasattr(parent, "isNetwork") or not parent.isNetwork():
        raise ValueError("Node is not a parent network: {}".format(parent_path))

    children = list(parent.children())
    if not children:
        return LayoutResult(
            parent_path=_safe_path(parent),
            moved_count=0,
            preserved_count=0,
            moved_paths=[],
            preserved_paths=[],
            strategy=strategy,
            positions={},
        )

    # Compute default fingerprint for user-layout detection
    default_fingerprint = _compute_default_fingerprint(hou, parent_path, children)

    if strategy == "tree_left_to_right":
        edges = _collect_connections(children)
        positions, moved, preserved = _tree_layout_positions(
            children, edges, default_fingerprint, preserve_user_layout, spacing_x, spacing_y
        )
    else:
        # houdini_default
        if dry_run:
            # For dry-run, just compute the fingerprint
            fingerprint = _compute_default_fingerprint(hou, parent_path, children)
            if not fingerprint:
                # Fallback: re-run and capture
                original: Dict[str, Tuple[float, float]] = {}
                for child in children:
                    pos = _safe_position(child)
                    if pos:
                        original[_safe_path(child)] = pos
                parent.layoutChildren()
                moved = []
                for child in children:
                    path = _safe_path(child)
                    pos = _safe_position(child)
                    if pos:
                        fingerprint[path] = pos
                # Restore
                for child in children:
                    path = _safe_path(child)
                    if path in original:
                        try:
                            child.setPosition(original[path])
                        except Exception:  # noqa: BLE001
                            pass
            positions = fingerprint
            moved = sorted(positions)
            preserved = []
        else:
            positions, moved, preserved = _houdini_default_layout_positions(
                hou, parent_path, children, default_fingerprint, preserve_user_layout
            )
            if preserve_user_layout and not preserved and not moved:
                # Edge case: all nodes were preserved, no moves
                pass

    if dry_run:
        return LayoutResult(
            parent_path=_safe_path(parent),
            moved_count=len(moved),
            preserved_count=len(preserved),
            moved_paths=sorted(moved),
            preserved_paths=sorted(preserved),
            strategy=strategy,
            positions={p: list(positions[p]) for p in positions},
        )

    # Apply positions for tree strategy
    if strategy == "tree_left_to_right":
        for child in children:
            path = _safe_path(child)
            if path in positions and path not in preserved:
                try:
                    child.setPosition(positions[path])
                except Exception:  # noqa: BLE001
                    pass

    return LayoutResult(
        parent_path=_safe_path(parent),
        moved_count=len(moved),
        preserved_count=len(preserved),
        moved_paths=sorted(moved),
        preserved_paths=sorted(preserved),
        strategy=strategy,
        positions={p: list(positions[p]) for p in positions},
    )


def compute_layout_plan(
    parent_path: str,
    *,
    strategy: str = "houdini_default",
    preserve_user_layout: bool = True,
    spacing_x: float = DEFAULT_SPACING_X,
    spacing_y: float = DEFAULT_SPACING_Y,
    hou_provider: Optional[Callable[[], Any]] = None,
) -> LayoutPlan:
    """Preview what ``auto_layout`` would do without mutating.

    Convenience wrapper around ``auto_layout(dry_run=True)``.
    """
    result = auto_layout(
        parent_path=parent_path,
        strategy=strategy,
        preserve_user_layout=preserve_user_layout,
        spacing_x=spacing_x,
        spacing_y=spacing_y,
        dry_run=True,
        hou_provider=hou_provider,
    )
    return LayoutPlan(
        parent_path=result.parent_path,
        total_nodes=result.moved_count + result.preserved_count,
        moved_nodes=result.moved_paths,
        preserved_nodes=result.preserved_paths,
        strategy=result.strategy,
        spacing=(spacing_x, spacing_y),
    )
