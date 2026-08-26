"""Append a verified PolyBevel SOP for selected edges."""

from __future__ import annotations

import math
from typing import Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_scalar_parm_verified,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def bevel_edges(
    input_path: str,
    group: str,
    distance: float,
    divisions: int = 1,
    node_name: Optional[str] = None,
) -> dict:
    """Bevel selected edges and verify the resulting SOP."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty string")
    if not isinstance(group, str) or not group.strip():
        return skill_error("Invalid bevel group", "group must be a non-empty edge selection")
    if isinstance(distance, bool) or not isinstance(distance, (int, float)):
        return skill_error("Invalid bevel distance", "distance must be numeric")
    resolved_distance = float(distance)
    if not math.isfinite(resolved_distance) or not 0 < resolved_distance <= 1_000_000.0:
        return skill_error("Invalid bevel distance", "distance must be finite, positive, and at most 1000000")
    if isinstance(divisions, bool) or not isinstance(divisions, int) or not 1 <= divisions <= 64:
        return skill_error("Invalid bevel divisions", "divisions must be an integer from 1 through 64")
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, input_path)
        before = geometry_readback(source)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "polybevel", node_name))
            requested = {"group": group, "distance": resolved_distance, "divisions": divisions}
            actual = {
                "group": str(set_scalar_parm_verified(created, ("group",), group)),
                "distance": float(set_scalar_parm_verified(created, ("distance",), resolved_distance, ("Distance",))),
                "divisions": int(set_scalar_parm_verified(created, ("divisions", "divs"), divisions, ("Divisions",))),
            }
            if actual != requested:
                raise RuntimeError("PolyBevel parameter readback did not match the request")
            readback = cook_readback(created, before=before)
            result = skill_success(
                "Created and verified PolyBevel SOP",
                input_path=source.path(),
                node=node_summary(created),
                parameters=requested,
                readback=readback,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create verified PolyBevel SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return bevel_edges(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
