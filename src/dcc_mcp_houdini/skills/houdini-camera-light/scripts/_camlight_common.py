"""Shared helpers for Houdini camera/light skills."""

from __future__ import annotations

from typing import Any, Optional, Sequence

# Friendly light type -> hlight 'light_type' menu index (hlight::2.0).
LIGHT_TYPES = {
    "point": 0,
    "line": 1,
    "grid": 2,
    "disk": 3,
    "sphere": 4,
    "tube": 5,
    "geometry": 6,
    "distant": 7,
    "sun": 7,
    "environment": 8,
}


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


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


def eval_parm(node: Any, name: str) -> Optional[Any]:
    """Eval a scalar parm or parm tuple if present, else None."""
    parm_tuple = node.parmTuple(name)
    if parm_tuple is not None:
        try:
            return list(parm_tuple.eval())
        except Exception:  # noqa: BLE001
            return None
    parm = node.parm(name)
    if parm is not None:
        try:
            return parm.eval()
        except Exception:  # noqa: BLE001
            return None
    return None


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def apply_transform(
    node: Any,
    translate: Optional[Sequence[float]],
    rotate: Optional[Sequence[float]],
    scale: Optional[Sequence[float]] = None,
) -> dict:
    """Set t/r/s parm tuples defensively; return what was applied."""
    applied: dict = {}
    if translate is not None and set_parm_if_exists(node, "t", translate):
        applied["t"] = list(translate)
    if rotate is not None and set_parm_if_exists(node, "r", rotate):
        applied["r"] = list(rotate)
    if scale is not None and set_parm_if_exists(node, "s", scale):
        applied["s"] = list(scale)
    return applied
