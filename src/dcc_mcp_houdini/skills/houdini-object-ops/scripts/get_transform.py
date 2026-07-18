"""Read the local transform (translate/rotate/scale) of an OBJ node."""

from __future__ import annotations

from _object_common import get_node, read_parm_tuple  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_transform(node_path: str) -> dict:
    """Return translate/rotate/scale parm values for *node_path*.

    Works on OBJ-level nodes that expose ``t``, ``r``, and ``s`` parm tuples.
    Missing tuples are returned as ``None`` rather than failing.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        translate = read_parm_tuple(node, "t")
        rotate = read_parm_tuple(node, "r")
        scale = read_parm_tuple(node, "s")
        if translate is None and rotate is None and scale is None:
            return skill_error(
                "No transform parameters",
                "Node has no t/r/s parm tuples: {}".format(node_path),
                possible_solutions=["Target an OBJ-level transformable node"],
            )
        return skill_success(
            "Read transform",
            node_path=node.path(),
            translate=translate,
            rotate=rotate,
            scale=scale,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read transform")


@skill_entry
def main(**kwargs) -> dict:
    return get_transform(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
