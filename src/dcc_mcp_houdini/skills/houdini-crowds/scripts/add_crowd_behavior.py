"""Attach a crowd behavior node to a crowd solver."""

from contextlib import ExitStack

from _crowd_common import validate_choice
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    next_free_input,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
)

BEHAVIOR_TYPES = {
    "steer": "crowd_steer",
    "avoid": "crowd_avoid",
    "seek": "crowd_seek",
    "follow": "crowd_follow",
    "trigger": "crowd_trigger",
    "geometry": "crowd_geometry",
    "pop": "crowd_pop",
}


def _find_solver(network):
    for child in network.children():
        name = child.type().name().split("::")[0]
        if name == "crowdsolver":
            return child
    return None


def add_crowd_behavior(
    network_path: str,
    behavior_type: str,
    node_name: str = None,
    parameters=None,
    connect_to: str = None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = validate_choice(behavior_type, BEHAVIOR_TYPES, "behavior_type")
        node_name = validate_identifier(node_name or node_type + "1")
        network = require_category(get_node(hou, network_path), "Dop", children=True)
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(network, node_type, node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            target = _find_solver(network) if connect_to is None else get_node(hou, connect_to)
            attached_index = None
            if target is not None:
                if target.parent() is not network:
                    raise ValueError("connect_to must name a node inside {}".format(network.path()))
                attached_index = next_free_input(target)
                target.setInput(attached_index, created)
            return skill_success(
                "Added crowd behavior",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                behavior_type=behavior_type,
                network_path=network.path(),
                attached_to=target.path() if target is not None else None,
                attached_input_index=attached_index,
                applied_parameters=applied,
                setup_state="attached" if target is not None else "unattached",
                simulation_verified=False,
                required_setup=[] if target is not None else ["connect the behavior into the solver chain"],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to add crowd behavior")


@skill_entry
def main(**kwargs):
    return add_crowd_behavior(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
