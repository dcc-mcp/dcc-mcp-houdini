"""Bounded heightfield readback: layer names and bounds without cooking."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import cooked_geometry, get_node, hou_missing_error, node_summary, volume_readback


def inspect_heightfield(node_path: str, max_names: int = 16) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(max_names, int) or isinstance(max_names, bool):
            raise ValueError("max_names must be an integer")
        if not 1 <= max_names <= 64:
            raise ValueError("max_names must be between 1 and 64")
        node = get_node(hou, node_path)
        summary = node_summary(node)
        geometry = cooked_geometry(node)
        if geometry is None:
            return skill_success(
                "Inspected heightfield without cooked geometry",
                node=summary,
                geometry_available=False,
                layer_names=[],
                layer_names_available=False,
                prim_count=None,
                point_count=None,
                bounding_box=None,
                valid=not summary["errors"],
                validation_scope="node_diagnostics_only",
            )
        readback = volume_readback(geometry, max_names=max_names, name_attribute="name")
        return skill_success(
            "Inspected heightfield",
            node=summary,
            geometry_available=True,
            layer_names=readback["volume_names"],
            layer_count=len(readback["volume_names"]),
            layer_names_available=readback["names_available"],
            prim_count=readback["prim_count"],
            point_count=readback["point_count"],
            bounding_box=readback["bounding_box"],
            valid=not summary["errors"],
            validation_scope="cached_geometry_readback",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect heightfield")


@skill_entry
def main(**kwargs):
    return inspect_heightfield(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
