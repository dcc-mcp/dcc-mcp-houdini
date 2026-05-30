"""Shared helpers for Houdini animation/channel/timeline skills."""

from __future__ import annotations

from typing import Any, Optional


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def get_parm(node: Any, parm_name: str) -> Any:
    """Return a parameter on *node* or raise a useful error."""
    parm = node.parm(parm_name)
    if parm is None:
        raise ValueError("No parameter named {!r} on {}".format(parm_name, node.path()))
    return parm


def keyframe_dict(kf: Any) -> dict:
    """Serialise a hou.Keyframe to a JSON-safe dict (defensive)."""
    entry: dict = {}
    for attr in ("frame", "value"):
        fn = getattr(kf, attr, None)
        if callable(fn):
            try:
                entry[attr] = fn()
            except Exception:  # noqa: BLE001
                entry[attr] = None
    expression = None
    expr_fn = getattr(kf, "expression", None)
    if callable(expr_fn):
        try:
            expression = expr_fn()
        except Exception:  # noqa: BLE001 - raised when no expression is set
            expression = None
    entry["expression"] = expression or None
    slope_fn = getattr(kf, "slope", None)
    if callable(slope_fn):
        try:
            slope = slope_fn()
            if isinstance(slope, (int, float)):
                entry["slope"] = slope
        except Exception:  # noqa: BLE001
            pass
    return entry


def parm_is_animated(parm: Any) -> bool:
    """True when a parm has keyframes or is otherwise time-dependent."""
    keyframes = getattr(parm, "keyframes", None)
    if callable(keyframes):
        try:
            if len(keyframes()):
                return True
        except Exception:  # noqa: BLE001
            pass
    is_td = getattr(parm, "isTimeDependent", None)
    if callable(is_td):
        try:
            return bool(is_td())
        except Exception:  # noqa: BLE001
            return False
    return False
