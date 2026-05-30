"""Shared helpers for Houdini node-graph skills."""

from __future__ import annotations

from typing import Any


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def paths_or_none(nodes) -> list:
    """Map a sequence of (possibly None) nodes to their paths or None."""
    result = []
    for node in nodes:
        result.append(node.path() if node is not None else None)
    return result
