"""Bounded UV readback: UV sets and UDIM tiles without cooking."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    cooked_geometry,
    get_node,
    hou_missing_error,
    node_summary,
    udim_tiles,
    uv_attribute_names,
    uv_values,
)


def inspect_uv(node_path: str, max_sets: int = 8) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(max_sets, int) or isinstance(max_sets, bool):
            raise ValueError("max_sets must be an integer")
        if not 1 <= max_sets <= 32:
            raise ValueError("max_sets must be between 1 and 32")
        node = get_node(hou, node_path)
        summary = node_summary(node)
        geometry = cooked_geometry(node)
        if geometry is None:
            return skill_success(
                "Inspected UV node without cooked geometry",
                node=summary,
                geometry_available=False,
                uv_sets=[],
                uv_set_count=0,
                udim_tiles=[],
                udim_detection="unavailable",
                valid=not summary["errors"],
                validation_scope="node_diagnostics_only",
            )
        names = uv_attribute_names(geometry, max_names=max_sets)
        tiles = []
        detection = "no_uv_sets"
        if names:
            values = uv_values(geometry, names[0])
            if values is None:
                detection = "no_values"
            else:
                tiles = udim_tiles(values)
                detection = "computed"
        return skill_success(
            "Inspected UV node",
            node=summary,
            geometry_available=True,
            uv_sets=names,
            uv_set_count=len(names),
            udim_tiles=tiles,
            udim_tile_count=len(tiles),
            udim_detection=detection,
            sampled_uv_set=names[0] if names else None,
            valid=not summary["errors"],
            validation_scope="cached_geometry_readback",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect UVs")


@skill_entry
def main(**kwargs):
    return inspect_uv(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
