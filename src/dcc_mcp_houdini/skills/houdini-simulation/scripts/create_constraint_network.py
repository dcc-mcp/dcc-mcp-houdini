"""Create a DOP constraint network with an optional relationship SOP."""

from contextlib import ExitStack

from _simulation_common import CONSTRAINT_TYPES, apply_parameters, validate_choice
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
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
        sop_parent = (
            require_category(get_node(hou, relationship_parent), "Sop", children=True)
            if (relationship_parent)
            else None
        )
        with ExitStack() as stack:
            network = dopnet.node(network_name)
            created_network = network is None
            if created_network:
                network = stack.enter_context(owned_node(dopnet, "constraintnetwork", network_name))
            relationship = None
            if sop_parent is not None:
                relationship = sop_parent.node(relationship_name)
                if relationship is None:
                    relationship = stack.enter_context(owned_node(sop_parent, relation_type, relationship_name))
            overrides = dict(parameters or {})
            if relationship is not None:
                overrides.setdefault("soppath", relationship.path())
            applied, skipped = stack.enter_context(apply_parameters(network, overrides))
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
                    "author the constraint geometry the relationship SOP reads",
                    "simulation cook",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create constraint network")


@skill_entry
def main(**kwargs):
    return create_constraint_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
