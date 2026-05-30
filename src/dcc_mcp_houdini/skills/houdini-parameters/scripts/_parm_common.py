"""Shared helpers for Houdini parameter skills."""

from __future__ import annotations

from typing import Any


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
