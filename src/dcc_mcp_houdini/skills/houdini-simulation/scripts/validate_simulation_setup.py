"""Validate a DOP network before a long simulation cook."""

from __future__ import annotations

from _simulation_common import SOLVER_TYPES, validate_simulation_type
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import base_node_type, get_node, hou_missing_error, node_summary, require_category


def validate_simulation_setup(network_path: str, simulation_type: str = None) -> dict:
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_missing_error()
    try:
        network = require_category(get_node(hou, network_path), "Dop", children=True)
        expected = validate_simulation_type(simulation_type) if simulation_type else None
        children = list(network.children())
        solver_children = []
        child_errors = []
        child_warnings = []
        for child in children:
            summary = node_summary(child)
            child_errors.extend("{}: {}".format(child.path(), error) for error in summary["errors"])
            child_warnings.extend("{}: {}".format(child.path(), warning) for warning in summary["warnings"])
            if base_node_type(summary["type"]).lower().endswith("solver"):
                solver_children.append(summary)
                if not child.inputs() or not any(child.inputs()):
                    child_errors.append("{}: solver has no object/source input".format(child.path()))
        errors = list(node_summary(network).get("errors", []))
        warnings = list(node_summary(network).get("warnings", []))
        errors.extend(child_errors)
        warnings.extend(child_warnings)
        if not solver_children:
            errors.append("No simulation solver found in DOP network")
        if expected and not any(base_node_type(item["type"]) == SOLVER_TYPES[expected] for item in solver_children):
            errors.append("Expected {} solver ({}) was not found".format(expected, SOLVER_TYPES[expected]))
        return skill_success(
            "Validated simulation setup",
            network_path=network.path(),
            simulation_type=expected,
            valid=not errors,
            validation_scope="structure_and_cached_diagnostics",
            simulation_verified=False,
            errors=errors,
            warnings=warnings,
            solver_count=len(solver_children),
            solvers=solver_children,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate simulation setup")


@skill_entry
def main(**kwargs) -> dict:
    return validate_simulation_setup(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
