"""Shared helpers for Houdini parameter skills."""

from __future__ import annotations

from typing import Any, Optional


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def template_info(template: Any) -> dict:
    """Return a small, JSON-safe parm-template summary."""
    info: dict = {"name": _safe(template, "name"), "label": _safe(template, "label")}
    data_type = getattr(template, "dataType", None)
    if callable(data_type):
        try:
            info["data_type"] = str(template.dataType())
        except Exception:  # noqa: BLE001
            info["data_type"] = None
    type_obj = getattr(template, "type", None)
    if callable(type_obj):
        try:
            info["template_type"] = str(template.type())
        except Exception:  # noqa: BLE001
            info["template_type"] = None
    num = getattr(template, "numComponents", None)
    if callable(num):
        try:
            info["num_components"] = int(template.numComponents())
        except Exception:  # noqa: BLE001
            info["num_components"] = None
    return info


def _safe(obj: Any, method: str):
    fn = getattr(obj, method, None)
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def coerce_scalar(value: Any, current: Any) -> Any:
    """Best-effort coercion of *value* to the type of *current*."""
    if current is None or isinstance(value, type(current)):
        return value
    try:
        if isinstance(current, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if isinstance(current, int):
            return int(value)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, str):
            return str(value)
    except (TypeError, ValueError):
        return value
    return value


def channel_write_conflict(parm: Any) -> Optional[str]:
    """Return why a plain value write would be unsafe, or ``None``.

    ``hou.Parm.set`` writes at the current frame. On an animated channel that
    can create a new keyframe instead of replacing the channel, so callers that
    promise plain value assignment must inspect the channel before mutating it.
    Inspection failures are conflicts: preserving an unknown channel is safer
    than reporting a write that may not have changed its evaluated value.
    """
    name = _safe(parm, "name") or "<unknown>"
    try:
        keyframe_count = len(parm.keyframes())
    except Exception as exc:  # noqa: BLE001
        return "Cannot safely inspect keyframes for parameter {!r}: {}".format(name, exc)
    if keyframe_count:
        return (
            "Parameter {!r} has {} keyframe(s); set_parms preserves keyframed and expression-driven channels. "
            "Use houdini-animation tools to edit or clear the channel first."
        ).format(name, keyframe_count)

    try:
        is_time_dependent = bool(parm.isTimeDependent())
    except Exception as exc:  # noqa: BLE001
        return "Cannot safely inspect time dependence for parameter {!r}: {}".format(name, exc)
    if is_time_dependent:
        return (
            "Parameter {!r} is time-dependent; set_parms preserves expression-driven channels. "
            "Use houdini-animation tools to edit or clear the channel first."
        ).format(name)
    return None
