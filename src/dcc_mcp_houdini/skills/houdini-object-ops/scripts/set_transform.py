"""Set the local transform (translate/rotate/scale) of an OBJ node."""

from __future__ import annotations

from typing import List, Optional

from _object_common import get_node, set_parm_tuple  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_transform(
    node_path: str,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> dict:
    """Set the ``t``/``r``/``s`` parm tuples for *node_path*.

    Only the supplied components are written. Components whose parm tuple is
    absent on the node are reported under ``unsupported``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        requested = {"t": translate, "r": rotate, "s": scale}
        applied = {}
        unsupported = []
        for parm_name, values in requested.items():
            if values is None:
                continue
            if set_parm_tuple(node, parm_name, values):
                applied[parm_name] = [float(v) for v in values]
            else:
                unsupported.append(parm_name)
        if not applied:
            return skill_error(
                "No transform applied",
                "Provide translate, rotate, and/or scale for a transformable node",
                unsupported=unsupported,
            )
        return skill_success(
            "Set transform",
            node_path=node.path(),
            applied=applied,
            unsupported=unsupported,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set transform")


@skill_entry
def main(**kwargs) -> dict:
    return set_transform(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
