"""Append a Normal SOP to compute geometry normals."""

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

# normal 'type' menu indices: 0=point, 1=vertex, 2=primitive, 3=detail.
_NORMAL_TYPE = {"point": 0, "vertex": 1, "primitive": 2, "detail": 3}


def add_normals(
    input_path: str,
    attribute_class: str = "point",
    node_name: Optional[str] = None,
) -> dict:
    """Create a Normal SOP downstream of *input_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = None
    try:
        source = get_node(hou, input_path)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "normal", node_name))
            type_index = _NORMAL_TYPE.get(attribute_class.lower())
            if type_index is not None:
                set_parm_if_exists(created, "type", type_index)
            result = skill_success(
                "Created normal SOP",
                input_path=source.path(),
                node=node_summary(created),
                attribute_class=attribute_class.lower(),
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create normal SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return add_normals(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
