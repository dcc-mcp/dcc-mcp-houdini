"""Safety policy for Houdini cooks that would otherwise run on the UI thread."""

from __future__ import annotations

import re
from typing import Any, Optional

DEFAULT_MAX_INLINE_INPUT_POINTS = 500_000
_PRIVATE_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|private|var|tmp)/)",
    re.IGNORECASE,
)


def public_exception_message(exc: Exception) -> str:
    """Preserve useful messages unless they appear to contain host paths."""
    message = str(exc).strip()
    if not message or _PRIVATE_PATH.search(message):
        return type(exc).__name__
    return message


def assess_inline_cook(
    node: Any,
    *,
    max_input_points: int = DEFAULT_MAX_INLINE_INPUT_POINTS,
) -> Optional[dict]:
    """Return a rejection payload when cached direct inputs are too large.

    Houdini HOM cooks are UI-thread-affine. Core ``execution: async`` changes
    transport semantics but cannot preempt a single blocking ``node.cook``.
    This conservative check inspects direct input geometry before mutation and
    routes known-heavy work to the adapter's isolated hython cook contract.
    Unavailable geometry is ignored so existing lightweight behavior remains.
    """
    inputs_method = getattr(node, "inputs", None)
    if not callable(inputs_method):
        return None
    try:
        inputs = tuple(item for item in inputs_method() if item is not None)
    except Exception:  # noqa: BLE001
        return None

    total_points = 0
    measured_inputs = 0
    for input_node in inputs:
        geometry_method = getattr(input_node, "geometry", None)
        if not callable(geometry_method):
            continue
        try:
            geometry = geometry_method()
            point_count_method = getattr(geometry, "pointCount", None)
            if not callable(point_count_method):
                continue
            count = int(point_count_method())
        except Exception:  # noqa: BLE001
            continue
        if count < 0:
            continue
        measured_inputs += 1
        total_points += count
        if total_points > max_input_points:
            return {
                "input_point_count": total_points,
                "measured_input_count": measured_inputs,
                "max_inline_input_points": max_input_points,
                "recommended_tool": "houdini_nodes__start_cook_job",
                "reason": "direct_input_point_limit_exceeded",
            }
    return None
