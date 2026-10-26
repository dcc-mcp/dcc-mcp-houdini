"""Create a DOP constraint network with an optional relationship DOP."""

from contextlib import ExitStack

from _simulation_common import CONSTRAINT_TYPES, apply_parameters, validate_choice
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    base_node_type,
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    require_category,
    validate_identifier,
)


def create_constraint_network(
    dopnet_path: str,
    constraint_type: str,
    network_name: str = "constraintnetwork1",
    relationship_parent: str = None,
    relationship_name: str = None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        relation_type = validate_choice(constraint_type, CONSTRAINT_TYPES, "constraint_type")
        validate_identifier(network_name)
        relationship_name = validate_identifier(relationship_name or relation_type)
        dopnet = require_category(get_node(hou, dopnet_path), "Dop", children=True)
        relation_parent = (
            require_category(get_node(hou, relationship_parent), "Dop", children=True)
            if (relationship_parent)
            else None
        )
        if relation_parent is not None and relation_parent != dopnet:
            raise ValueError("relationship_parent must be the same DOP network as dopnet_path")
        if relation_parent is not None and network_name == relationship_name:
            raise ValueError("network_name and relationship_name must be different")
        network = dopnet.node(network_name)
        if network is not None and base_node_type(network.type().name()) != "constraintnetwork":
            raise ValueError("Existing network_name must name a constraintnetwork DOP")
        relationship = relation_parent.node(relationship_name) if relation_parent is not None else None
        if relationship is not None and base_node_type(relationship.type().name()) != relation_type:
            raise ValueError("Existing relationship_name must name a {} DOP".format(relation_type))
        if network is not None and relation_parent is not None:
            for connection in network.inputConnections():
                if connection.inputIndex() == 1 and (
                    connection.inputItem() != relationship or connection.inputItemOutputIndex() != 0
                ):
                    raise ValueError("Constraint network relationship input is already connected to another node")
        with ExitStack() as stack:
            created_network = network is None
            if created_network:
                network = stack.enter_context(owned_node(dopnet, "constraintnetwork", network_name))
            if relation_parent is not None and relationship is None:
                relationship = stack.enter_context(owned_node(relation_parent, relation_type, relationship_name))
            applied, skipped = stack.enter_context(apply_parameters(network, parameters))
            connected = False
            try:
                if relationship is not None and not any(c.inputIndex() == 1 for c in network.inputConnections()):
                    network.setInput(1, relationship)
                    connected = True
                return skill_success(
                    "Created constraint network",
                    node=node_summary(network),
                    network_path=network.path(),
                    constraint_type=constraint_type,
                    created_network=created_network,
                    relationship_path=relationship.path() if relationship is not None else None,
                    applied_parameters=applied,
                    skipped_parameters=skipped,
                    setup_state="skeleton",
                    simulation_verified=False,
                    required_setup=[
                        "wire the constraint network to the solved object",
                        "set soppath to constraint geometry whose constraint_name matches the relationship Data Name",
                        "simulation cook",
                    ],
                )
            except BaseException:
                if connected:
                    network.setInput(1, None)
                raise
    except Exception as exc:
        return skill_exception(exc, message="Failed to create constraint network")


@skill_entry
def main(**kwargs):
    return create_constraint_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
