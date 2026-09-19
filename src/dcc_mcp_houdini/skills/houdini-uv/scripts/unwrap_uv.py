"""Create a UV unwrap SOP wired into a modelling chain."""

from contextlib import ExitStack

from _uv_common import UNWRAP_TYPES, validate_choice
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


def unwrap_uv(
    parent_path: str, unwrap_type: str, source_path: str = None, node_name: str = None, parameters=None
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = validate_choice(unwrap_type, UNWRAP_TYPES, "unwrap_type")
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
                "Created UV unwrap node",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                unwrap_type=unwrap_type,
                source_path=source.path() if source is not None else None,
                wired=wired,
                applied_parameters=applied,
                setup_state="wired" if wired else "unwired",
                required_setup=[
                    "cook the node to generate UVs",
                    "pack the islands with layout_uv",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create UV unwrap node")


@skill_entry
def main(**kwargs):
    return unwrap_uv(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
