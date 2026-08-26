"""Revolve a profile through a verified native Revolve SOP."""

from __future__ import annotations

import math
from typing import List, Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_scalar_parm_verified,
    set_tuple_parm_verified,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def lathe_profile(
    profile: str,
    axis: str = "y",
    origin: Optional[List[float]] = None,
    segments: int = 32,
    node_name: Optional[str] = None,
) -> dict:
    """Revolve one curve/profile SOP and verify parameter and geometry readback."""
    if not isinstance(profile, str) or not profile:
        return skill_error("Invalid lathe profile", "profile must be a non-empty node path")
    if axis not in _AXES:
        return skill_error("Invalid lathe axis", "axis must be one of: x, y, z")
    resolved_origin = origin if origin is not None else [0.0, 0.0, 0.0]
    if (
        not isinstance(resolved_origin, (list, tuple))
        or len(resolved_origin) != 3
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or abs(float(value)) > 1_000_000.0
            for value in resolved_origin
        )
    ):
        return skill_error("Invalid lathe origin", "origin must contain three bounded finite numbers")
    if isinstance(segments, bool) or not isinstance(segments, int) or not 3 <= segments <= 256:
        return skill_error("Invalid lathe segments", "segments must be an integer from 3 through 256")
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, profile)
        before = geometry_readback(source)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "revolve", node_name))
            origin_values = set_tuple_parm_verified(created, ("origin",), tuple(resolved_origin), ("Origin",))
            direction_values = set_tuple_parm_verified(created, ("dir",), _AXES[axis], ("Axis Direction",))
            set_scalar_parm_verified(created, ("divs",), segments, ("Divisions",))
            readback = cook_readback(created, before=before)
            result = skill_success(
                "Created and verified Revolve SOP",
                profile=source.path(),
                node=node_summary(created),
                parameters={
                    "axis": axis,
                    "axis_direction": list(direction_values),
                    "origin": list(origin_values),
                    "segments": segments,
                },
                readback=readback,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create verified Revolve SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return lathe_profile(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
