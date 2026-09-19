"""Create a pyro post-process SOP that shapes a cached simulation after the fact."""

from contextlib import ExitStack

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


def add_pyro_post_process(
    parent_path: str,
    source_path: str = None,
    node_name: str = "pyropostprocess1",
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        validate_identifier(node_name)
        parent = require_category(get_node(hou, parent_path), "Sop", children=True)
        source = get_node(hou, source_path) if source_path else None
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, "pyropostprocess", node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            wired = False
            if source is not None:
                created.setInput(0, source)
                wired = True
            return skill_success(
                "Added pyro post-process",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                source_path=source.path() if source is not None else None,
                wired=wired,
                applied_parameters=applied,
                setup_state="wired" if wired else "unwired",
                simulation_verified=False,
                required_setup=[
                    "feed the node from a DOP import of the cached simulation",
                    "cook before reading the reshaped volume back",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to add pyro post-process")


@skill_entry
def main(**kwargs):
    return add_pyro_post_process(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
