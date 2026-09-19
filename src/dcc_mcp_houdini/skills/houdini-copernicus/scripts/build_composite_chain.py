"""Build a sequential Copernicus composite chain in a single owned transaction."""

from contextlib import ExitStack

from _cop_common import resolve_filter_type
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
    validate_parameters,
)

MAX_STEPS = 16


def _validate_steps(steps):
    if not isinstance(steps, (list, tuple)) or not steps:
        raise ValueError("steps must be a non-empty list")
    if len(steps) > MAX_STEPS:
        raise ValueError("steps must contain at most {} entries".format(MAX_STEPS))
    normalized = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError("step {} must be an object".format(index))
        filter_type = step.get("filter_type")
        if not isinstance(filter_type, str) or not filter_type:
            raise ValueError("step {} requires filter_type".format(index))
        node_name = step.get("node_name")
        if node_name is not None:
            validate_identifier(node_name, "step {} node_name".format(index))
        parameters = step.get("parameters")
        validate_parameters(parameters)
        normalized.append((resolve_filter_type(filter_type), node_name, parameters or {}))
    return normalized


def build_composite_chain(network_path: str, steps, source_path: str = None) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        resolved_steps = _validate_steps(steps)
        network = require_category(get_node(hou, network_path), "Cop", children=True)
        source = get_node(hou, source_path) if source_path else None
        with ExitStack() as stack:
            created = []
            previous = source
            for node_type, node_name, parameters in resolved_steps:
                node = stack.enter_context(owned_node(network, node_type, node_name))
                applied = stack.enter_context(parameter_edit(node, parameters))
                wired = False
                if previous is not None:
                    node.setInput(0, previous)
                    wired = True
                created.append(
                    {
                        "node_path": node.path(),
                        "node_type": node.type().name(),
                        "applied_parameters": applied,
                        "wired": wired,
                        "errors": list(node.errors()),
                        "warnings": list(node.warnings()),
                    }
                )
                previous = node
            return skill_success(
                "Built composite chain",
                network_path=network.path(),
                node_count=len(created),
                nodes=created,
                first_node_path=created[0]["node_path"],
                last_node_path=created[-1]["node_path"],
                source_path=source.path() if source is not None else None,
                setup_state="wired" if source is not None else "unwired",
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to build composite chain")


@skill_entry
def main(**kwargs):
    return build_composite_chain(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
