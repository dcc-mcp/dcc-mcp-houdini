"""Add a bounded PolySplit loop/path and verify cooked geometry."""

from __future__ import annotations

from typing import Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_scalar_parm_verified,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def add_edge_loop(input_path: str, split_locations: str, node_name: Optional[str] = None) -> dict:
    """Append PolySplit with an explicit bounded split-location expression."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty node path")
    if (
        not isinstance(split_locations, str)
        or not split_locations.strip()
        or len(split_locations) > 4096
        or "\x00" in split_locations
    ):
        return skill_error(
            "Invalid split locations",
            "split_locations must be a non-empty Houdini selection string of at most 4096 characters",
        )
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
        created = make_downstream_sop(source, "polysplit", node_name)
        set_scalar_parm_verified(
            created,
            ("splitloc", "splitlocations"),
            split_locations,
            ("Split Locations",),
        )
        readback = cook_readback(created, before=before)
        return skill_success(
            "Created and verified PolySplit SOP",
            input_path=source.path(),
            node=node_summary(created),
            parameters={"split_locations": split_locations},
            readback=readback,
        )
    except Exception as exc:
        if created is not None:
            try:
                created.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(exc, message="Failed to create verified PolySplit SOP")


@skill_entry
def main(**kwargs) -> dict:
    return add_edge_loop(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
