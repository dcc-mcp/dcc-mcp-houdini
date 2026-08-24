"""Build a bounded radial instance array with Circle and Copy to Points."""

from __future__ import annotations

import math
from typing import Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_menu_parm_candidates,
    set_scalar_parm_verified,
    set_tuple_parm_verified,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_ORIENTATION_LABELS = {
    "x": ("yz plane", "yz"),
    "y": ("zx plane", "xz plane", "zx", "xz"),
    "z": ("xy plane", "xy"),
}


def array_instances(
    input_path: str,
    count: int,
    radius: float,
    axis: str = "y",
    node_name: Optional[str] = None,
    points_node_name: Optional[str] = None,
) -> dict:
    """Instance one SOP on a generated radial point ring and verify output."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty node path")
    if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 128:
        return skill_error("Invalid array count", "count must be an integer from 2 through 128")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)):
        return skill_error("Invalid array radius", "radius must be numeric")
    resolved_radius = float(radius)
    if not math.isfinite(resolved_radius) or not 0 < resolved_radius <= 1_000_000.0:
        return skill_error("Invalid array radius", "radius must be finite, positive, and at most 1000000")
    if axis not in _ORIENTATION_LABELS:
        return skill_error("Invalid array axis", "axis must be one of: x, y, z")
    for value, label in ((node_name, "node_name"), (points_node_name, "points_node_name")):
        if value is not None and (not isinstance(value, str) or not value):
            return skill_error("Invalid node name", "{} must be non-empty when provided".format(label))

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    points = None
    created = None
    try:
        source = get_node(hou, input_path)
        parent = source.parent()
        if parent is None:
            raise ValueError("Input node has no parent SOP network")
        before = geometry_readback(source)
        points = parent.createNode("circle", node_name=points_node_name)
        set_menu_parm_candidates(
            points,
            ("type", "primitivetype"),
            ("polygon",),
            ("Primitive Type",),
        )
        set_menu_parm_candidates(
            points,
            ("orient", "orientation"),
            _ORIENTATION_LABELS[axis],
            ("Orientation",),
        )
        set_scalar_parm_verified(points, ("divs", "divisions"), count, ("Divisions",))
        set_tuple_parm_verified(points, ("rad", "radius"), (resolved_radius, resolved_radius), ("Radius",))
        points_readback = cook_readback(points, require_change=False)

        created = make_downstream_sop(source, "copytopoints", node_name)
        created.setInput(1, points)
        readback = cook_readback(created, before=before)
        readback["points"] = points_readback
        return skill_success(
            "Created and verified radial Copy to Points array",
            input_path=source.path(),
            node=node_summary(created),
            points_node=node_summary(points),
            parameters={"axis": axis, "count": count, "radius": resolved_radius},
            readback=readback,
        )
    except Exception as exc:
        for node in (created, points):
            if node is not None:
                try:
                    node.destroy()
                except Exception:  # noqa: BLE001
                    pass
        return skill_exception(exc, message="Failed to create verified radial instance array")


@skill_entry
def main(**kwargs) -> dict:
    return array_instances(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
