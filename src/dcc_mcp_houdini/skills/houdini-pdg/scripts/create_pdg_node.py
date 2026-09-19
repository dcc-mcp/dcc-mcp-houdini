"""Create a Top node with parameter and input readback.

Parameter overrides are applied through ``parameter_edit``: a name the node does
not expose fails the call and rolls back, so this tool has no
``skipped_parameters`` output.
"""

from contextlib import ExitStack

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    input_connections,
    owned_node,
    parameter_edit,
    require_category,
    resolve_inputs,
    validate_node_type,
    validate_parameters,
)


def create_pdg_node(
    network_path: str, node_type: str, node_name: str = None, input_nodes=None, parameters=None
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        network = require_category(get_node(hou, network_path), "Top", children=True)
        node_type = validate_node_type(node_type)
        validate_parameters(parameters)
        sources = resolve_inputs(hou, network, input_nodes)
        with ExitStack() as stack:
            node = stack.enter_context(owned_node(network, node_type, node_name))
            applied = stack.enter_context(parameter_edit(node, parameters))
            for index, source in enumerate(sources):
                node.setInput(index, source)
            wired = input_connections(node)
            if [(item["input_index"], item["source_path"]) for item in wired] != list(
                enumerate(s.path() for s in sources)
            ):
                raise RuntimeError("Input wiring readback mismatch")
            return skill_success(
                "Created Top node",
                network_path=network.path(),
                node_path=node.path(),
                node_type=node.type().name(),
                applied_parameters=applied,
                wired_inputs=wired,
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create Top node")


@skill_entry
def main(**kwargs):
    return create_pdg_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
