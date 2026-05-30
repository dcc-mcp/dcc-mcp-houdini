"""Shared helpers for Houdini material skills."""

from __future__ import annotations

from typing import Any

from dcc_mcp_core.skill import skill_error


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def hou_import_error() -> dict:
    """Standard error when the HOM module is unavailable."""
    return skill_error("Houdini not available", "hou could not be imported")


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def set_parm_value(node: Any, name: str, value: Any) -> None:
    """Set either a scalar parm or a tuple parm."""
    if isinstance(value, (list, tuple)):
        parm_tuple = node.parmTuple(name)
        if parm_tuple is not None:
            parm_tuple.set(tuple(value))
            return

    parm = node.parm(name)
    if parm is None:
        raise ValueError("Parameter {!r} not found on {}".format(name, node.path()))
    parm.set(value)
