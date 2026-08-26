"""Append a Blast SOP to delete (or keep) a selected group."""

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

# Blast 'grouptype' menu indices (Houdini 18.5+).
_GROUP_TYPE = {
    "guess": 0,
    "breakpoints": 1,
    "edges": 2,
    "points": 3,
    "prims": 4,
    "primitives": 4,
    "vertices": 5,
}


def blast_geometry(
    input_path: str,
    group: str,
    group_type: str = "prims",
    delete_non_selected: bool = False,
    node_name: Optional[str] = None,
) -> dict:
    """Create a Blast SOP that deletes (or keeps) *group* downstream of input."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = None
    try:
        source = get_node(hou, input_path)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "blast", node_name))
            set_parm_if_exists(created, "group", group)
            type_index = _GROUP_TYPE.get(group_type.lower())
            if type_index is not None:
                set_parm_if_exists(created, "grouptype", type_index)
            # negate=1 keeps the selection and deletes everything else.
            set_parm_if_exists(created, "negate", 1 if delete_non_selected else 0)
            result = skill_success(
                "Created blast SOP",
                input_path=source.path(),
                node=node_summary(created),
                group=group,
                group_type=group_type.lower(),
                delete_non_selected=bool(delete_non_selected),
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create blast SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return blast_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
