"""List point/primitive/vertex/detail attributes for a SOP node."""

from __future__ import annotations

from _geo_common import attrib_entries, cooked_geometry, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_attributes(node_path: str) -> dict:
    """Return attribute names/types grouped by class (point/prim/vertex/detail)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        geo = cooked_geometry(node)
        attribs = {
            "point": attrib_entries(geo.pointAttribs()) if hasattr(geo, "pointAttribs") else [],
            "primitive": attrib_entries(geo.primAttribs()) if hasattr(geo, "primAttribs") else [],
            "vertex": attrib_entries(geo.vertexAttribs()) if hasattr(geo, "vertexAttribs") else [],
            "detail": attrib_entries(geo.globalAttribs()) if hasattr(geo, "globalAttribs") else [],
        }
        return skill_success(
            "Listed attributes",
            node_path=node.path(),
            attributes=attribs,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list attributes")


@skill_entry
def main(**kwargs) -> dict:
    return list_attributes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
