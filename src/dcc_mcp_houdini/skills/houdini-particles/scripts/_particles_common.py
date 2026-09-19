"""POP network authoring helpers shared by the particle skill tools."""

from contextlib import ExitStack

from dcc_mcp_core.skill import skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
    validate_parameters,
)

SOLVER_NAME = "popsolver"

FORCE_TYPES = {
    "force": "popforce",
    "wind": "popwind",
    "drag": "popdrag",
    "vortex": "popvortex",
    "attract": "popattract",
    "axis": "popaxisforce",
}

BEHAVIOR_TYPES = {
    "kill": "popkill",
    "replicate": "popreplicate",
    "split": "popsplit",
    "limit": "poplimit",
    "collide": "popcollide",
    "steer": "popsteer",
}


def base_type(type_name):
    """Strip a Houdini ``name::version`` suffix so overrides stay comparable."""
    parts = type_name.split("::")
    if len(parts) > 1 and parts[-1][:1].isdigit():
        parts.pop()
    return parts[-1]


def validate_choice(value, mapping, label):
    if value not in mapping:
        raise ValueError("Unsupported {}: {!r}".format(label, value))
    return mapping[value]


def find_pop_solver(network):
    """Return the first ``popsolver`` child, or ``None`` when there is none."""
    for child in network.children():
        if base_type(child.type().name()) == SOLVER_NAME:
            return child
    return None


def next_free_input(node, limit=32):
    """First free input index of a node, bounded so a bad graph cannot loop."""
    used = set()
    for connection in node.inputConnections():
        used.add(connection.inputIndex())
    for index in range(limit):
        if index not in used:
            return index
    raise ValueError("No free input available on {}".format(node.path()))


def connections_summary(node):
    return [
        {
            "input_index": connection.inputIndex(),
            "source_path": connection.inputItem().path(),
        }
        for connection in node.inputConnections()
    ]


def resolve_target(hou, network, connect_to):
    """Pick the node a new POP node attaches to, or ``None`` to leave it loose."""
    if connect_to is None:
        return find_pop_solver(network)
    target = get_node(hou, connect_to)
    if target.parent() is not network:
        raise ValueError("connect_to must name a node inside {}".format(network.path()))
    return target


def attach_pop_node(hou, network_path, node_type, node_name=None, parameters=None, connect_to=None, kind="POP"):
    """Create a POP node inside ``network_path`` and attach it to the solver."""
    validate_parameters(parameters)
    node_name = validate_identifier(node_name or node_type + "1")
    network = require_category(get_node(hou, network_path), "Dop", children=True)
    target = resolve_target(hou, network, connect_to)
    with ExitStack() as stack:
        created = stack.enter_context(owned_node(network, node_type, node_name))
        applied = stack.enter_context(parameter_edit(created, parameters))
        attached_index = None
        if target is not None:
            attached_index = next_free_input(target)
            target.setInput(attached_index, created)
        return skill_success(
            "Created {} node".format(kind),
            node=node_summary(created),
            node_path=created.path(),
            node_type=created.type().name(),
            network_path=network.path(),
            attached_to=target.path() if target is not None else None,
            attached_input_index=attached_index,
            applied_parameters=applied,
            skipped_parameters=[],
            connections=connections_summary(created),
            setup_state="attached" if target is not None else "unattached",
            simulation_verified=False,
            required_setup=[] if target is not None else ["connect the POP node into the solver chain"],
        )
