"""Append a Group Create SOP to define a point/primitive/edge group."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _mesh_common import get_node, make_downstream_sop, node_summary, set_parm_if_exists  # noqa: E402

# groupcreate 'grouptype' menu indices.
_GROUP_TYPE = {
    "points": 0,
    "prims": 1,
    "primitives": 1,
    "edges": 2,
    "vertices": 3,
}


def group_geometry(
    input_path: str,
    group_name: str,
    group_type: str = "prims",
    pattern: Optional[str] = None,
    node_name: Optional[str] = None,
) -> dict:
    """Create a Group Create SOP downstream of *input_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, input_path)
        group_node = make_downstream_sop(source, "groupcreate", node_name)
        set_parm_if_exists(group_node, "groupname", group_name)
        type_index = _GROUP_TYPE.get(group_type.lower())
        if type_index is not None:
            set_parm_if_exists(group_node, "grouptype", type_index)
        if pattern:
            # Enable base-group pattern selection when supported.
            set_parm_if_exists(group_node, "groupbase", 1)
            set_parm_if_exists(group_node, "basegroup", pattern)
        return skill_success(
            "Created group SOP",
            input_path=source.path(),
            node=node_summary(group_node),
            group_name=group_name,
            group_type=group_type.lower(),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create group SOP")


@skill_entry
def main(**kwargs) -> dict:
    return group_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
