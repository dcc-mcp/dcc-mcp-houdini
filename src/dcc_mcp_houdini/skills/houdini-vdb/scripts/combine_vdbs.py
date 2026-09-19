"""Combine two VDB inputs through a single typed call."""

from contextlib import ExitStack

from _vdb_common import resolve_vdb_sources, wire_inputs
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


def combine_vdbs(
    parent_path: str,
    source_a_path: str,
    source_b_path: str,
    node_name: str = "vdbcombine1",
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        validate_identifier(node_name)
        parent = require_category(get_node(hou, parent_path), "Sop", children=True)
        source_a, source_b = resolve_vdb_sources(hou, parent, [source_a_path, source_b_path])
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, "vdbcombine", node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            wired = wire_inputs(created, [source_a, source_b])
            return skill_success(
                "Combined VDB inputs",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                source_paths=[source_a.path(), source_b.path()],
                wired_inputs=wired,
                applied_parameters=applied,
                setup_state="wired",
                required_setup=["set the vdbcombine operation parameter to choose the boolean"],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to combine VDB inputs")


@skill_entry
def main(**kwargs):
    return combine_vdbs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
