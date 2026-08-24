"""Set and verify the local pivot of a Houdini OBJ node."""

from __future__ import annotations

import math
from typing import List

from _object_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_pivot(node_path: str, position: List[float]) -> dict:
    """Set the ``p`` parm tuple and return exact readback."""
    if not isinstance(node_path, str) or not node_path:
        return skill_error("Invalid node", "node_path must be a non-empty string")
    if (
        not isinstance(position, (list, tuple))
        or len(position) != 3
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or abs(float(value)) > 1_000_000.0
            for value in position
        )
    ):
        return skill_error("Invalid pivot", "position must contain three bounded finite numbers")
    requested = tuple(float(value) for value in position)

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    parm_tuple = None
    previous = None
    try:
        node = get_node(hou, node_path)
        parm_tuple = node.parmTuple("p")
        if parm_tuple is None:
            raise ValueError("Node has no local pivot parameter tuple: {}".format(node.path()))
        previous = tuple(float(value) for value in parm_tuple.eval())
        parm_tuple.set(requested)
        actual = tuple(float(value) for value in parm_tuple.eval())
        if len(actual) != 3 or any(abs(actual[index] - requested[index]) > 1e-8 for index in range(3)):
            raise RuntimeError("Pivot parameter readback did not match the request")
        values = list(actual)
        return skill_success(
            "Set and verified pivot",
            node_path=node.path(),
            position=values,
            readback={"pivot": values, "verified": True},
        )
    except Exception as exc:
        if parm_tuple is not None and previous is not None:
            try:
                parm_tuple.set(previous)
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(exc, message="Failed to set and verify pivot")


@skill_entry
def main(**kwargs) -> dict:
    return set_pivot(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
