"""Shared helpers for Houdini object-operation skills."""

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


def read_parm_tuple(node: Any, name: str):
    """Return a parm-tuple value as a list of floats, or ``None`` if absent."""
    parm_tuple = node.parmTuple(name)
    if parm_tuple is None:
        return None
    return [float(v) for v in parm_tuple.eval()]


def set_parm_tuple(node: Any, name: str, values) -> bool:
    """Set a parm-tuple value; return ``True`` when the tuple exists."""
    parm_tuple = node.parmTuple(name)
    if parm_tuple is None:
        return False
    parm_tuple.set(tuple(values))
    return True
