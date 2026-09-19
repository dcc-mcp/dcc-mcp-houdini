"""Add a heightfield layer SOP and wire it into a terrain chain."""

from contextlib import ExitStack

from _terrain_common import TERRAIN_LAYER_TYPES, validate_choice
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
)


def add_terrain_layer(
    parent_path: str,
    layer_type: str,
    source_path: str = None,
    node_name: str = None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = validate_choice(layer_type, TERRAIN_LAYER_TYPES, "layer_type")
        node_name = validate_identifier(node_name or node_type + "1")
        parent = require_category(get_node(hou, parent_path), "Sop", children=True)
        source = get_node(hou, source_path) if source_path else None
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, node_type, node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            wired = False
            if source is not None:
                created.setInput(0, source)
                wired = True
            return skill_success(
                "Added terrain layer",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                layer_type=layer_type,
                source_path=source.path() if source is not None else None,
                wired=wired,
                applied_parameters=applied,
                setup_state="wired" if wired else "unwired",
                required_setup=[] if wired else ["wire the layer into the heightfield chain"],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to add terrain layer")


@skill_entry
def main(**kwargs):
    return add_terrain_layer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
