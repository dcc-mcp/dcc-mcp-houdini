"""Append a verified PolyExtrude SOP for a primitive selection."""

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

_LIMIT = 1_000_000.0
_TOLERANCE = 1e-8


def _number(value: object, name: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, skill_error("Invalid extrusion", "{} must be numeric".format(name))
    result = float(value)
    if not math.isfinite(result) or abs(result) > _LIMIT:
        return None, skill_error(
            "Invalid extrusion",
            "{} must be finite and within +/-{}".format(name, int(_LIMIT)),
        )
    return result, None


def extrude_faces(
    input_path: str,
    group: Optional[str] = None,
    distance: float = 0.0,
    inset: float = 0.0,
    node_name: Optional[str] = None,
) -> dict:
    """Extrude selected primitives and verify the cooked SOP readback."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty string")
    if group is not None and (not isinstance(group, str) or not group.strip()):
        return skill_error("Invalid group", "group must be a non-empty string when provided")
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")
    resolved_distance, error = _number(distance, "distance")
    if error:
        return error
    resolved_inset, error = _number(inset, "inset")
    if error:
        return error
    if abs(resolved_distance) <= _TOLERANCE and abs(resolved_inset) <= _TOLERANCE:
        return skill_error("Extrusion has no effect", "distance or inset must be non-zero")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, input_path)
        before = geometry_readback(source)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "polyextrude", node_name))
            requested = {
                "group": group or "",
                "distance": resolved_distance,
                "inset": resolved_inset,
            }
            actual = {
                "group": str(set_scalar_parm_verified(created, ("group",), requested["group"])),
                "distance": float(
                    set_scalar_parm_verified(
                        created,
                        ("dist", "distance"),
                        resolved_distance,
                        ("Distance",),
                    )
                ),
                "inset": float(set_scalar_parm_verified(created, ("inset",), resolved_inset, ("Inset",))),
            }
            if actual["group"] != requested["group"] or any(
                abs(actual[key] - requested[key]) > _TOLERANCE for key in ("distance", "inset")
            ):
                raise RuntimeError("PolyExtrude parameter readback did not match the request")
            after = cook_readback(created, before=before)
            result = skill_success(
                "Created and verified PolyExtrude SOP",
                input_path=source.path(),
                node=node_summary(created),
                parameters=requested,
                readback=after,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create verified PolyExtrude SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return extrude_faces(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
