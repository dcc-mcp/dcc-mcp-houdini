"""Append a Group Create SOP to define a point/primitive/edge group."""

from __future__ import annotations

from typing import Optional

from _mesh_common import (  # noqa: E402
    get_node,
    make_downstream_sop,
    node_summary,
    set_parm_if_exists,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

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

    created = None
    try:
        source = get_node(hou, input_path)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "groupcreate", node_name))
            set_parm_if_exists(created, "groupname", group_name)
            type_index = _GROUP_TYPE.get(group_type.lower())
            if type_index is not None:
                set_parm_if_exists(created, "grouptype", type_index)
            if pattern:
                # Enable base-group pattern selection when supported.
                set_parm_if_exists(created, "groupbase", 1)
                set_parm_if_exists(created, "basegroup", pattern)
            result = skill_success(
                "Created group SOP",
                input_path=source.path(),
                node=node_summary(created),
                group_name=group_name,
                group_type=group_type.lower(),
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create group SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return group_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
