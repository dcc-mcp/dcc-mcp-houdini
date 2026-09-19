"""Create a heightfield SOP, the entry node of a Houdini terrain chain."""

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


def create_heightfield(parent_path: str, node_name: str = "heightfield1", parameters=None) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        validate_identifier(node_name)
        parent = require_category(get_node(hou, parent_path), "Sop", children=True)
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, "heightfield", node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            return skill_success(
                "Created heightfield",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                applied_parameters=applied,
                setup_state="skeleton",
                required_setup=[
                    "size the heightfield for the shot",
                    "add terrain layers (noise, erode, terrace, scatter)",
                    "add a heightfield_output node before rendering",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create heightfield")


@skill_entry
def main(**kwargs):
    return create_heightfield(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
