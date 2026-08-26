"""Bridge two named edge/face groups through a verified PolyBridge SOP."""

from __future__ import annotations

from typing import Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_scalar_parm_verified,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def bridge_edges(
    input_path: str,
    source_group: str,
    destination_group: str,
    divisions: int = 1,
    node_name: Optional[str] = None,
) -> dict:
    """Append PolyBridge and verify its group/division and cooked readback."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty node path")
    if not isinstance(source_group, str) or not source_group.strip():
        return skill_error("Invalid source group", "source_group must be a non-empty selection")
    if not isinstance(destination_group, str) or not destination_group.strip():
        return skill_error("Invalid destination group", "destination_group must be a non-empty selection")
    if source_group == destination_group:
        return skill_error("Invalid bridge groups", "source and destination groups must differ")
    if isinstance(divisions, bool) or not isinstance(divisions, int) or not 1 <= divisions <= 64:
        return skill_error("Invalid bridge divisions", "divisions must be an integer from 1 through 64")
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, input_path)
        before = geometry_readback(source)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "polybridge", node_name))
            set_scalar_parm_verified(created, ("srcgroup",), source_group)
            set_scalar_parm_verified(created, ("dstgroup",), destination_group)
            set_scalar_parm_verified(created, ("divisions", "divs"), divisions, ("Divisions",))
            readback = cook_readback(created, before=before)
            result = skill_success(
                "Created and verified PolyBridge SOP",
                input_path=source.path(),
                node=node_summary(created),
                parameters={
                    "destination_group": destination_group,
                    "divisions": divisions,
                    "source_group": source_group,
                },
                readback=readback,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create verified PolyBridge SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return bridge_edges(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
