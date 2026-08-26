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
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

_ORIENTATION_LABELS = {
    "x": ("yz plane", "yz"),
    "y": ("zx plane", "xz plane", "zx", "xz"),
    "z": ("xy plane", "xy"),
}

_AXIS_VECTORS = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}

_SOURCE_FORWARD_VECTORS = {
    "+x": (1.0, 0.0, 0.0),
    "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0),
    "-y": (0.0, -1.0, 0.0),
    "+z": (0.0, 0.0, 1.0),
    "-z": (0.0, 0.0, -1.0),
}


def _orientation_vex(axis: str, direction_mode: str, source_forward: str) -> str:
    ring_axis = _AXIS_VECTORS[axis]
    forward = _SOURCE_FORWARD_VECTORS[source_forward]
    target_expression = "normalize(cross(ring_axis, radial))" if direction_mode == "tangent" else "radial"
    return """vector ring_axis = set({axis_x}, {axis_y}, {axis_z});
vector source_forward = set({forward_x}, {forward_y}, {forward_z});
vector radial = @P - dot(@P, ring_axis) * ring_axis;
i@dcc_mcp_orientation_valid = 0;
if (length2(radial) > 1e-12) {{
    radial = normalize(radial);
    vector target = {target};
    if (length2(target) > 1e-12) {{
        p@orient = quaternion(dihedral(source_forward, normalize(target)));
        i@dcc_mcp_orientation_valid = 1;
    }}
}}
""".format(
        axis_x=ring_axis[0],
        axis_y=ring_axis[1],
        axis_z=ring_axis[2],
        forward_x=forward[0],
        forward_y=forward[1],
        forward_z=forward[2],
        target=target_expression,
    )


def _cross(left: tuple, right: tuple) -> tuple:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _normalized(vector: tuple) -> tuple:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-6:
        raise RuntimeError("Generated point orientation contains a degenerate direction")
    return tuple(value / length for value in vector)


def _rotated_by_quaternion(vector: tuple, quaternion: tuple) -> tuple:
    imaginary = quaternion[:3]
    crossed = _cross(imaginary, vector)
    nested = _cross(imaginary, crossed)
    return tuple(vector[index] + 2.0 * quaternion[3] * crossed[index] + 2.0 * nested[index] for index in range(3))


def _orientation_readback(
    node,
    expected_count: int,
    axis: str,
    direction_mode: str,
    source_forward: str,
) -> dict:
    geometry = node.geometry()
    point_count = int(geometry.pointCount())
    if point_count != expected_count:
        raise RuntimeError("Generated point count does not match requested array count")

    orient_attribute = geometry.findPointAttrib("orient")
    if orient_attribute is None or int(orient_attribute.size()) != 4:
        raise RuntimeError("Generated points are missing a quaternion orient attribute")
    raw_orientations = tuple(float(value) for value in geometry.pointFloatAttribValues("orient"))
    if len(raw_orientations) != point_count * 4:
        raise RuntimeError("Generated orient attribute has an invalid value count")
    orientations = tuple(raw_orientations[index : index + 4] for index in range(0, len(raw_orientations), 4))
    if any(
        not all(math.isfinite(value) for value in quaternion)
        or not 0.999 <= sum(value * value for value in quaternion) <= 1.001
        for quaternion in orientations
    ):
        raise RuntimeError("Generated orient attribute contains invalid quaternions")

    position_attribute = geometry.findPointAttrib("P")
    if position_attribute is None or int(position_attribute.size()) != 3:
        raise RuntimeError("Generated points are missing position readback")
    raw_positions = tuple(float(value) for value in geometry.pointFloatAttribValues("P"))
    if len(raw_positions) != point_count * 3:
        raise RuntimeError("Generated point position has an invalid value count")
    positions = tuple(raw_positions[index : index + 3] for index in range(0, len(raw_positions), 3))

    ring_axis = _AXIS_VECTORS[axis]
    forward = _SOURCE_FORWARD_VECTORS[source_forward]
    for position, quaternion in zip(positions, orientations):
        projection = sum(position[index] * ring_axis[index] for index in range(3))
        radial = _normalized(tuple(position[index] - projection * ring_axis[index] for index in range(3)))
        target = _normalized(_cross(ring_axis, radial)) if direction_mode == "tangent" else radial
        actual = _normalized(_rotated_by_quaternion(forward, quaternion))
        alignment = sum(actual[index] * target[index] for index in range(3))
        if alignment < 0.999:
            raise RuntimeError("Generated orient attribute does not match the requested direction")

    valid_attribute = geometry.findPointAttrib("dcc_mcp_orientation_valid")
    if valid_attribute is None or int(valid_attribute.size()) != 1:
        raise RuntimeError("Generated points are missing orientation validity readback")
    validity = tuple(int(value) for value in geometry.pointIntAttribValues("dcc_mcp_orientation_valid"))
    if len(validity) != point_count or any(value != 1 for value in validity):
        raise RuntimeError("Generated point orientation contains a degenerate direction")

    distinct_count = len({tuple(round(value, 8) for value in item) for item in orientations})
    if distinct_count < 2:
        raise RuntimeError("Generated point orientations do not vary around the array")
    return {
        "attribute": "orient",
        "distinct_count": distinct_count,
        "point_count": point_count,
        "tuple_size": 4,
        "valid_count": sum(validity),
        "verified": True,
    }


def array_instances(
    input_path: str,
    count: int,
    radius: float,
    axis: str = "y",
    start_angle_degrees: float = 0.0,
    direction_mode: str = "radial",
    source_forward: str = "+x",
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
    if isinstance(start_angle_degrees, bool) or not isinstance(start_angle_degrees, (int, float)):
        return skill_error("Invalid start angle", "start_angle_degrees must be numeric")
    resolved_start_angle = float(start_angle_degrees)
    if not math.isfinite(resolved_start_angle) or abs(resolved_start_angle) > 360_000.0:
        return skill_error(
            "Invalid start angle",
            "start_angle_degrees must be finite and within -360000 through 360000",
        )
    if direction_mode not in ("radial", "tangent"):
        return skill_error("Invalid direction mode", "direction_mode must be radial or tangent")
    if source_forward not in _SOURCE_FORWARD_VECTORS:
        return skill_error(
            "Invalid source forward",
            "source_forward must be one of: +x, -x, +y, -y, +z, -z",
        )
    for value, label in ((node_name, "node_name"), (points_node_name, "points_node_name")):
        if value is not None and (not isinstance(value, str) or not value):
            return skill_error("Invalid node name", "{} must be non-empty when provided".format(label))

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    points = None
    orientation = None
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
        rotation = {
            "x": (resolved_start_angle, 0.0, 0.0),
            "y": (0.0, resolved_start_angle, 0.0),
            "z": (0.0, 0.0, resolved_start_angle),
        }[axis]
        set_tuple_parm_verified(points, ("r", "rotate"), rotation, ("Rotate", "Rotation"))
        points_readback = cook_readback(points, require_change=False)

        orientation = make_downstream_sop(points, "attribwrangle")
        set_menu_parm_candidates(
            orientation,
            ("class", "runover"),
            ("points", "point"),
            ("Run Over",),
        )
        set_scalar_parm_verified(
            orientation,
            ("snippet", "vex"),
            _orientation_vex(axis, direction_mode, source_forward),
            ("VEXpression", "Snippet"),
        )
        orientation_readback = cook_readback(orientation, require_change=False)
        orientation_receipt = _orientation_readback(
            orientation,
            count,
            axis,
            direction_mode,
            source_forward,
        )

        created = make_downstream_sop(source, "copytopoints", node_name)
        created.setInput(1, orientation)
        readback = cook_readback(created, before=before)
        readback["points"] = points_readback
        readback["orientation_cook"] = orientation_readback
        readback["orientation"] = orientation_receipt
        return skill_success(
            "Created and verified radial Copy to Points array",
            input_path=source.path(),
            node=node_summary(created),
            points_node=node_summary(points),
            orientation_node=node_summary(orientation),
            parameters={
                "axis": axis,
                "count": count,
                "direction_mode": direction_mode,
                "radius": resolved_radius,
                "source_forward": source_forward,
                "start_angle_degrees": resolved_start_angle,
            },
            readback=readback,
        )
    except Exception:  # noqa: BLE001
        for node in (created, orientation, points):
            if node is not None:
                try:
                    node.destroy()
                except Exception:  # noqa: BLE001
                    pass
        return skill_error(
            "Failed to create verified radial instance array",
            "Houdini rejected the bounded radial-array transaction",
        )


@skill_entry
def main(**kwargs) -> dict:
    return array_instances(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
