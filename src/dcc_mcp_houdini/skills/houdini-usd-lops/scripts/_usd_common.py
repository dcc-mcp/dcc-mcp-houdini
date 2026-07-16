"""Shared, dependency-free helpers for read-only USD inspection."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Tuple


def require_absolute_path(value: str, label: str) -> str:
    """Validate and return an absolute Houdini or USD path."""
    path = str(value or "").strip()
    if not path.startswith("/"):
        raise ValueError("{} must be an absolute path".format(label))
    return path


def require_range(value: int, label: str, minimum: int, maximum: int) -> int:
    """Validate an integer bound for callers that bypass JSON Schema."""
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError("{} must be an integer from {} to {}".format(label, minimum, maximum))
    return value


def resolve_stage(hou: Any, lop_node_path: str) -> Tuple[Any, Any]:
    """Resolve a Houdini LOP node and its composed USD Stage."""
    node_path = require_absolute_path(lop_node_path, "lop_node_path")
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    stage_method = getattr(node, "stage", None)
    if not callable(stage_method):
        raise ValueError("Houdini node is not a LOP node: {}".format(node_path))
    stage = stage_method()
    if stage is None:
        raise RuntimeError("LOP node returned no composed USD Stage: {}".format(node_path))
    return node, stage


def resolve_prim(stage: Any, prim_path: str) -> Any:
    """Resolve a valid prim from *stage*."""
    path = require_absolute_path(prim_path, "prim_path")
    prim = stage.GetPrimAtPath(path)
    if not prim:
        raise ValueError("USD prim not found: {}".format(path))
    return prim


def make_time_code(Usd: Any, value: Any) -> Any:
    """Create default or numeric ``Usd.TimeCode`` with finite-number validation."""
    if value is None:
        return Usd.TimeCode.Default()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("time_code must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("time_code must be a finite number")
    return Usd.TimeCode(number)


def _json_safe(value: Any, budget: Dict[str, int]) -> Tuple[Any, bool]:
    if value is None or isinstance(value, (bool, int, str)):
        return value, False
    if isinstance(value, float):
        return (value, False) if math.isfinite(value) else (str(value), False)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace"), False

    if isinstance(value, dict):
        output: Dict[str, Any] = {}
        truncated = False
        for key, item in value.items():
            if budget["remaining"] <= 0:
                truncated = True
                break
            budget["remaining"] -= 1
            output[str(key)], child_truncated = _json_safe(item, budget)
            truncated = truncated or child_truncated
        return output, truncated

    if not isinstance(value, (str, bytes)):
        try:
            iterator = iter(value)
        except TypeError:
            iterator = None
        if iterator is not None:
            output = []
            truncated = False
            while budget["remaining"] > 0:
                try:
                    item = next(iterator)
                except StopIteration:
                    break
                budget["remaining"] -= 1
                converted, child_truncated = _json_safe(item, budget)
                output.append(converted)
                truncated = truncated or child_truncated
            else:
                try:
                    next(iterator)
                except StopIteration:
                    pass
                else:
                    truncated = True
            return output, truncated

    path = getattr(value, "path", None)
    if isinstance(path, str):
        return path, False
    return str(value), False


def bounded_value(value: Any, max_items: int, max_chars: int) -> dict:
    """Return a JSON-safe value with explicit item and serialized-size bounds."""
    require_range(max_items, "max_value_items", 1, 256)
    require_range(max_chars, "max_value_chars", 64, 4096)
    converted, item_truncated = _json_safe(value, {"remaining": max_items})
    serialized = json.dumps(converted, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > max_chars:
        return {
            "value": None,
            "value_preview": serialized[:max_chars],
            "truncated": True,
            "truncation_reasons": ["characters"] + (["items"] if item_truncated else []),
        }
    return {
        "value": converted,
        "truncated": item_truncated,
        "truncation_reasons": ["items"] if item_truncated else [],
    }
