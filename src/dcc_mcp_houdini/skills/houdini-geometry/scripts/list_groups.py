"""List point/primitive/edge groups for a SOP node."""

from __future__ import annotations

from _geo_common import cooked_geometry, get_node, group_entries  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_groups(node_path: str) -> dict:
    """Return group names/counts grouped by class (point/primitive/edge)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        geo = cooked_geometry(node)
        groups = {
            "point": group_entries(geo.pointGroups(), "points") if hasattr(geo, "pointGroups") else [],
            "primitive": group_entries(geo.primGroups(), "prims") if hasattr(geo, "primGroups") else [],
            "edge": group_entries(geo.edgeGroups(), "edges") if hasattr(geo, "edgeGroups") else [],
        }
        return skill_success(
            "Listed groups",
            node_path=node.path(),
            groups=groups,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list groups")


@skill_entry
def main(**kwargs) -> dict:
    return list_groups(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
