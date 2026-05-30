"""Shared helpers for Houdini mesh-operation skills."""

from __future__ import annotations

from typing import Any, Optional


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def make_downstream_sop(input_node: Any, optype: str, name: Optional[str] = None) -> Any:
    """Create *optype* in the input's parent, wired to the input's output 0."""
    parent = input_node.parent()
    if parent is None:
        raise ValueError("Input node has no parent network: {}".format(input_node.path()))
    new_node = parent.createNode(optype, node_name=name)
    new_node.setInput(0, input_node)
    if hasattr(new_node, "moveToGoodPosition"):
        try:
            new_node.moveToGoodPosition()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(new_node, "setDisplayFlag"):
        new_node.setDisplayFlag(True)
    return new_node


def set_parm_if_exists(node: Any, name: str, value: Any) -> bool:
    """Set a scalar/tuple parm only when it exists. Return whether it was set."""
    if isinstance(value, (list, tuple)):
        parm_tuple = node.parmTuple(name)
        if parm_tuple is None:
            return False
        parm_tuple.set(tuple(value))
        return True
    parm = node.parm(name)
    if parm is None:
        return False
    parm.set(value)
    return True


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }
