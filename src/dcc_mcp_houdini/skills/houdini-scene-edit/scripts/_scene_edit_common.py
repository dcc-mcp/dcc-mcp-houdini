"""Shared helpers for Houdini scene-edit skills."""

from __future__ import annotations

from typing import Any


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def iter_nodes(root: Any, recursive: bool) -> list:
    """Return the children (or all descendants) of *root*."""
    if recursive and hasattr(root, "allSubChildren"):
        return list(root.allSubChildren())
    return list(root.children())


def vec_to_list(vec: Any) -> list:
    """Convert a HOM vector/tuple-like object to a plain list of floats."""
    try:
        return [float(component) for component in vec]
    except TypeError:
        # Some HOM vectors expose explicit accessors only.
        return [float(vec[i]) for i in range(len(vec))]
