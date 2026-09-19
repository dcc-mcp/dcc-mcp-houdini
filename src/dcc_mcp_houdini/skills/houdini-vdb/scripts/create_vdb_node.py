"""Create a VDB SOP with optional one or two input wiring."""

from contextlib import ExitStack

from _vdb_common import TWO_INPUT_TYPES, VDB_TYPES, resolve_vdb_sources, validate_choice, wire_inputs
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


def create_vdb_node(
    parent_path: str,
    vdb_type: str,
    source_path: str = None,
    source_b_path: str = None,
    node_name: str = None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = validate_choice(vdb_type, VDB_TYPES, "vdb_type")
        node_name = validate_identifier(node_name or node_type + "1")
        if source_b_path is not None and vdb_type not in TWO_INPUT_TYPES:
            raise ValueError("source_b_path is only supported for: {}".format(", ".join(sorted(TWO_INPUT_TYPES))))
        if source_b_path is not None and source_path is None:
            raise ValueError("source_b_path requires source_path; input 0 must not be left dangling")
        parent = require_category(get_node(hou, parent_path), "Sop", children=True)
        sources = resolve_vdb_sources(hou, parent, [source_path, source_b_path])
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, node_type, node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            wired = wire_inputs(created, sources)
            return skill_success(
                "Created VDB node",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                vdb_type=vdb_type,
                source_paths=[source.path() for source in sources if source is not None],
                wired_inputs=wired,
                applied_parameters=applied,
                setup_state="wired" if wired else "unwired",
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create VDB node")


@skill_entry
def main(**kwargs):
    return create_vdb_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
