"""Mirror geometry through a verified native Mirror SOP."""

from __future__ import annotations

import math
from typing import List, Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_tuple_parm_verified,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _vector(value: object, name: str):
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(
            isinstance(component, bool)
            or not isinstance(component, (int, float))
            or not math.isfinite(float(component))
            or abs(float(component)) > 1_000_000.0
            for component in value
        )
    ):
        return None, skill_error("Invalid mirror vector", "{} must contain three bounded finite numbers".format(name))
    return tuple(float(component) for component in value), None


def mirror(
    input_path: str,
    origin: Optional[List[float]] = None,
    direction: Optional[List[float]] = None,
    node_name: Optional[str] = None,
) -> dict:
    """Append Mirror, set its plane, and verify cooked geometry."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty node path")
    resolved_origin, error = _vector(origin or [0.0, 0.0, 0.0], "origin")
    if error:
        return error
    resolved_direction, error = _vector(direction or [1.0, 0.0, 0.0], "direction")
    if error:
        return error
    if sum(component * component for component in resolved_direction) <= 1e-16:
        return skill_error("Invalid mirror direction", "direction must be non-zero")
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = None
    try:
        source = get_node(hou, input_path)
        before = geometry_readback(source)
        created = make_downstream_sop(source, "mirror", node_name)
        actual_origin = set_tuple_parm_verified(created, ("origin",), resolved_origin, ("Origin",))
        actual_direction = set_tuple_parm_verified(
            created,
            ("dir",),
            resolved_direction,
            ("Direction",),
        )
        readback = cook_readback(created, before=before)
        return skill_success(
            "Created and verified Mirror SOP",
            input_path=source.path(),
            node=node_summary(created),
            parameters={"direction": list(actual_direction), "origin": list(actual_origin)},
            readback=readback,
        )
    except Exception as exc:
        if created is not None:
            try:
                created.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(exc, message="Failed to create verified Mirror SOP")


@skill_entry
def main(**kwargs) -> dict:
    return mirror(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
