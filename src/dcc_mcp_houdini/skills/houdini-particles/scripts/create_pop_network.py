"""Create a POP network skeleton with rollback and explicit missing setup."""

from contextlib import ExitStack

from _particles_common import SOLVER_NAME, base_type
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
    validate_parameters,
)


def create_pop_network(
    parent_path: str,
    network_name: str = "popnet1",
    solver_name: str = None,
    object_name: str = None,
    source_name: str = None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        validate_identifier(network_name)
        solver_name = validate_identifier(solver_name or SOLVER_NAME + "1")
        object_name = validate_identifier(object_name or "popobject1")
        source_name = validate_identifier(source_name or "popsource1")
        validate_parameters(parameters)
        parent = get_node(hou, parent_path)
        with ExitStack() as stack:
            network = parent.node(network_name)
            created_network = network is None
            if created_network:
                network = stack.enter_context(owned_node(parent, "popnet", network_name))
            require_category(network, "Dop", children=True)
            solver = network.node(solver_name)
            created_solver = solver is None
            if created_solver:
                solver = stack.enter_context(owned_node(network, SOLVER_NAME, solver_name))
            if base_type(solver.type().name()) != SOLVER_NAME:
                raise ValueError("Existing node is not a POP solver: {}".format(solver.path()))
            pop_object = network.node(object_name)
            if pop_object is None:
                pop_object = stack.enter_context(owned_node(network, "popobject", object_name))
            pop_source = network.node(source_name)
            if pop_source is None:
                pop_source = stack.enter_context(owned_node(network, "popsource", source_name))
            # DOP solvers take their simulated objects on input 0.
            solver.setInput(0, pop_object)
            applied = stack.enter_context(parameter_edit(solver, parameters))
            return skill_success(
                "Created POP network skeleton",
                network=node_summary(network),
                solver=node_summary(solver),
                network_path=network.path(),
                solver_path=solver.path(),
                object_path=pop_object.path(),
                source_path=pop_source.path(),
                created_network=created_network,
                created_solver=created_solver,
                applied_parameters=applied,
                setup_state="skeleton",
                simulation_verified=False,
                required_setup=[
                    "connect popsource to the solver chain",
                    "bind source geometry on popobject/popsource",
                    "simulation cook",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create POP network")


@skill_entry
def main(**kwargs):
    return create_pop_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
