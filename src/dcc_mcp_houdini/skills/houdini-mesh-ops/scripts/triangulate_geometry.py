"""Append a Divide SOP configured to triangulate (convex) polygons."""

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


def triangulate_geometry(input_path: str, node_name: Optional[str] = None) -> dict:
    """Create a Divide SOP downstream of *input_path* set to convex triangles."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = None
    try:
        source = get_node(hou, input_path)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "divide", node_name))
            # Convex polygons into triangles (max 3 sides).
            set_parm_if_exists(created, "convex", 1)
            set_parm_if_exists(created, "numsides", 3)
            result = skill_success(
                "Created triangulate (divide) SOP",
                input_path=source.path(),
                node=node_summary(created),
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create triangulate SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return triangulate_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
