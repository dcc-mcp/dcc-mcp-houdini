"""Create a typed node from one of four modern Houdini node families.

Resolves a readable alias (or a raw Houdini node type) to the real node type
for RBD material fracture, COps pyro, sparse GPU pyro, or rasterize Volume,
then creates the node in a parent network of the matching child category
(Sop/Cop/Dop), applies bounded parameter overrides, and wires existing input
nodes. Parameter overrides go through ``parameter_edit``: a name the node does
not expose fails the call and rolls back rather than being silently skipped.

This tool only creates and wires nodes. It never cooks, never claims a cooked
simulation, and never claims a rendered artifact.
"""

from contextlib import ExitStack

from _modern_sim import modern_node_meta
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    input_connections,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    resolve_inputs,
    validate_parameters,
)


def create_modern_sim_node(
    parent_path: str,
    node_type: str,
    node_name: str = None,
    input_nodes=None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        meta = modern_node_meta(node_type)
        resolved_type = meta["node_type"]
        category = meta["category"]
        family = meta["family"]
        validate_parameters(parameters)
        parent = require_category(get_node(hou, parent_path), category, children=True)
        sources = resolve_inputs(hou, parent, input_nodes)
        with ExitStack() as stack:
            node = stack.enter_context(owned_node(parent, resolved_type, node_name))
            applied = stack.enter_context(parameter_edit(node, parameters))
            for index, source in enumerate(sources):
                node.setInput(index, source)
            wired = input_connections(node)
            if [(item["input_index"], item["source_path"]) for item in wired] != list(
                enumerate(s.path() for s in sources)
            ):
                raise RuntimeError("Input wiring readback mismatch")
            return skill_success(
                "Created modern simulation node",
                node=node_summary(node),
                node_path=node.path(),
                node_type=node.type().name(),
                requested_node_type=node_type,
                resolved_node_type=resolved_type,
                family=family,
                category=category,
                parent_path=parent.path(),
                applied_parameters=applied,
                wired_inputs=wired,
                setup_state="wired" if sources else "unwired",
                required_setup=([] if sources else ["wire a source into the node's input 0 (if the node requires one)"])
                + ["verify parameter names on the target Houdini build before cooking", "cook and verify explicitly"],
                artifact_verified=False,
                simulation_verified=False,
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create modern simulation node")


@skill_entry
def main(**kwargs):
    return create_modern_sim_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
