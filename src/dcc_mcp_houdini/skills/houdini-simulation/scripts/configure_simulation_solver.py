"""Apply parameters with rollback through cook/readback failures."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary, parameter_edit, require_category


def configure_simulation_solver(solver_path: str, parameters, cook: bool = False) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(cook, bool):
            raise ValueError("cook must be boolean")
        solver = require_category(get_node(hou, solver_path), "Dop")
        with parameter_edit(solver, parameters) as applied:
            if cook:
                solver.cook(force=True)
            summary = node_summary(solver)
            if summary["errors"]:
                raise RuntimeError("Solver reports cook errors: {}".format(summary["errors"]))
            return skill_success(
                "Configured simulation solver",
                solver=summary,
                solver_path=solver.path(),
                applied_parameters=applied,
                cooked=cook,
                valid=True,
                validation_scope="parameters_and_cached_diagnostics",
                simulation_verified=False,
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure simulation solver")


@skill_entry
def main(**kwargs):
    return configure_simulation_solver(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
