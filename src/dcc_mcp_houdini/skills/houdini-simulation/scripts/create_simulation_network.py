"""Create a DOP solver skeleton with rollback and explicit missing setup."""

from contextlib import ExitStack

from _simulation_common import SOLVER_TYPES, validate_simulation_type
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    base_node_type,
    get_node,
    hou_missing_error,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
    validate_parameters,
)


def create_simulation_network(
    parent_path: str, simulation_type: str, network_name: str = "dopnet1", solver_name: str = None, parameters=None
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        kind = validate_simulation_type(simulation_type)
        validate_identifier(network_name)
        solver_name = validate_identifier(solver_name or "{}solver1".format(kind))
        validate_parameters(parameters)
        parent = get_node(hou, parent_path)
        with ExitStack() as stack:
            network = parent.node(network_name)
            created_network = network is None
            if created_network:
                network = stack.enter_context(owned_node(parent, "dopnet", network_name))
            require_category(network, "Dop", children=True)
            solver = network.node(solver_name)
            created_solver = solver is None
            if created_solver:
                solver = stack.enter_context(owned_node(network, SOLVER_TYPES[kind], solver_name))
            require_category(solver, "Dop")
            if base_node_type(solver.type().name()) != SOLVER_TYPES[kind]:
                raise ValueError("Existing solver has a different type")
            applied = stack.enter_context(parameter_edit(solver, parameters))
            return skill_success(
                "Created simulation skeleton",
                simulation_type=kind,
                solver_type=solver.type().name(),
                network_path=network.path(),
                solver_path=solver.path(),
                created_network=created_network,
                created_solver=created_solver,
                applied_parameters=applied,
                setup_state="skeleton",
                simulation_verified=False,
                required_setup=["object/source geometry", "solver inputs and output", "simulation cook"],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create simulation network")


@skill_entry
def main(**kwargs):
    return create_simulation_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
