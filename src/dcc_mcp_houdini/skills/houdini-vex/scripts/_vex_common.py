"""Shared helpers for houdini-vex skill scripts."""

from __future__ import annotations

from typing import Any, List

from dcc_mcp_houdini._vex_types import (
    VexContext,
    VexSyntaxError,
    WrangleType,
)


def resolve_vex_context(run_over: str) -> VexContext:
    """Map a run-over string to a :class:`VexContext` enum value."""
    _MAP: dict[str, VexContext] = {
        "points": VexContext.POINTS,
        "prims": VexContext.PRIMITIVES,
        "verts": VexContext.VERTICES,
        "detail": VexContext.DETAIL,
        "global": VexContext.GLOBAL_VERTICES,
        "attribs": VexContext.ATTRIBUTES,
        "numbers": VexContext.NUMBERS,
    }
    return _MAP.get(run_over.lower(), VexContext.POINTS)


def resolve_wrangle_type(type_name: str) -> WrangleType:
    """Map a string to a :class:`WrangleType` enum value."""
    for wt in WrangleType:
        if wt.value == type_name.lower():
            return wt
    return WrangleType.ATTRIB_WRANGLE


def format_validation_errors(errors: List[VexSyntaxError]) -> List[dict]:
    """Convert a list of :class:`VexSyntaxError` to JSON-compatible dicts."""
    return [e.to_dict() for e in errors]


def _get_node(hou: Any, node_path: str) -> Any:
    """Resolve a node path, raising ValueError if not found."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Houdini node not found: {node_path}")
    return node
