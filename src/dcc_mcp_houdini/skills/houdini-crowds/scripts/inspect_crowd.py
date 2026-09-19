"""Report the structure of a crowd network without simulating it."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, input_connections, node_summary


def inspect_crowd(network_path: str, max_nodes: int = 64) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(max_nodes, int) or isinstance(max_nodes, bool):
            raise ValueError("max_nodes must be an integer")
        if not 1 <= max_nodes <= 256:
            raise ValueError("max_nodes must be between 1 and 256")
        network = get_node(hou, network_path)
        children = network.children() if callable(getattr(network, "children", None)) else ()
        nodes = []
        for child in list(children)[:max_nodes]:
            summary = node_summary(child)
            summary["inputs"] = input_connections(child)
            nodes.append(summary)
        types = [node["type"] for node in nodes]
        return skill_success(
            "Inspected crowd network",
            network_path=network.path(),
            node_count=len(nodes),
            nodes=nodes,
            has_solver="crowdsolver" in types,
            has_agents="crowdobject" in types,
            behavior_count=sum(1 for name in types if name.startswith("crowd_")),
            truncated=len(children) > len(nodes),
            validation_scope="graph_structure",
            simulation_verified=False,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect crowd network")


@skill_entry
def main(**kwargs):
    return inspect_crowd(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
