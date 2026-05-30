"""Shared helpers for Houdini lookdev / shader-network skills."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ENV_PRESET_DIR = "DCC_MCP_HOUDINI_MATERIAL_PRESET_DIR"

# Parameter assignment for an object's material, in priority order.
MATERIAL_ASSIGN_PARMS = ("shop_materialpath", "shop_materialpath1")


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def preset_dir() -> Path:
    """Return the adapter-owned material-preset directory (created on demand)."""
    override = os.environ.get(ENV_PRESET_DIR)
    base = Path(override) if override else Path.home() / ".dcc-mcp" / "houdini" / "material_presets"
    base.mkdir(parents=True, exist_ok=True)
    return base


def coerce_scalar(value: Any, current: Any) -> Any:
    """Best-effort coerce *value* to the type of *current* (the parm's value)."""
    if current is None:
        return value
    try:
        if isinstance(current, bool):
            return bool(value)
        if isinstance(current, int) and not isinstance(current, bool):
            return int(value)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, str):
            return str(value)
    except (TypeError, ValueError):
        return value
    return value


def set_parameters(node: Any, parameters: dict) -> tuple:
    """Set parameters on *node*; return (applied, errors) dicts."""
    applied: dict = {}
    errors: dict = {}
    for name, value in parameters.items():
        try:
            if isinstance(value, (list, tuple)):
                parm_tuple = node.parmTuple(name)
                if parm_tuple is None:
                    errors[name] = "No parameter tuple named {!r}".format(name)
                    continue
                parm_tuple.set(tuple(value))
                applied[name] = list(value)
            else:
                parm = node.parm(name)
                if parm is None:
                    errors[name] = "No parameter named {!r}".format(name)
                    continue
                try:
                    current = parm.eval()
                except Exception:  # noqa: BLE001
                    current = None
                coerced = coerce_scalar(value, current)
                parm.set(coerced)
                applied[name] = coerced
        except Exception as exc:  # noqa: BLE001
            errors[name] = str(exc)
    return applied, errors


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }
