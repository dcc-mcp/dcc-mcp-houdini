"""Inspect a MaterialX subnetwork: node inventory, wiring and unwired inputs."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, input_connections, node_summary


def inspect_materialx_graph(material_path: str, max_nodes: int = 64) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(max_nodes, int) or isinstance(max_nodes, bool):
            raise ValueError("max_nodes must be an integer")
        if not 1 <= max_nodes <= 256:
            raise ValueError("max_nodes must be between 1 and 256")
        material = get_node(hou, material_path)
        children = material.children() if callable(getattr(material, "children", None)) else ()
        nodes = []
        unwired = []
        for child in list(children)[:max_nodes]:
            summary = node_summary(child)
            connections = input_connections(child)
            summary["inputs"] = connections
            nodes.append(summary)
            if not connections:
                unwired.append(child.path())
        outputs = [node["path"] for node in nodes if "output" in node["name"].lower()]
        return skill_success(
            "Inspected MaterialX graph",
            material_path=material.path(),
            node_count=len(nodes),
            nodes=nodes,
            unwired_nodes=unwired,
            output_candidates=outputs,
            truncated=len(children) > len(nodes),
            validation_scope="graph_structure",
            compiled=False,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect MaterialX graph")


@skill_entry
def main(**kwargs):
    return inspect_materialx_graph(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
