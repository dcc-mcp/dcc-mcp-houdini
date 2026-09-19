"""Create a crowd DOP network skeleton for agent simulation."""

from contextlib import ExitStack

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
)


def create_crowd_network(
    parent_path: str,
    network_name: str = "crowdsim1",
    solver_name: str = "crowdsolver1",
    object_name: str = "crowdobject1",
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        validate_identifier(network_name)
        solver_name = validate_identifier(solver_name)
        object_name = validate_identifier(object_name)
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
                solver = stack.enter_context(owned_node(network, "crowdsolver", solver_name))
            crowd_object = network.node(object_name)
            if crowd_object is None:
                crowd_object = stack.enter_context(owned_node(network, "crowdobject", object_name))
            # Parameter edits roll themselves back, but rewiring a *reused* solver
            # would not: the solver is not owned by this request, so a later
            # failure would leave our input 0 on someone else's network. Validate
            # by applying parameters first, and only then rewire.
            applied = stack.enter_context(parameter_edit(solver, parameters))
            solver.setInput(0, crowd_object)
            return skill_success(
                "Created crowd network skeleton",
                network=node_summary(network),
                solver=node_summary(solver),
                network_path=network.path(),
                solver_path=solver.path(),
                object_path=crowd_object.path(),
                created_network=created_network,
                created_solver=created_solver,
                applied_parameters=applied,
                setup_state="skeleton",
                simulation_verified=False,
                required_setup=[
                    "assign an agent definition to the crowd object",
                    "provide agent source geometry or a crowd source node",
                    "simulation cook",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create crowd network")


@skill_entry
def main(**kwargs):
    return create_crowd_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
