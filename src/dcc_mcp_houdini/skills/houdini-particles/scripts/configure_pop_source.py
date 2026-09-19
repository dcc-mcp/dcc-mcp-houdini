"""Apply bounded parameters to a POP node with rollback on cook failure."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    parameter_edit,
    require_category,
)


def configure_pop_source(node_path: str, parameters, cook: bool = False) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(cook, bool):
            raise ValueError("cook must be boolean")
        node = require_category(get_node(hou, node_path), "Dop")
        with parameter_edit(node, parameters) as applied:
            if cook:
                node.cook(force=True)
            summary = node_summary(node)
            if summary["errors"]:
                raise RuntimeError("Node reports cook errors: {}".format(summary["errors"]))
            return skill_success(
                "Configured POP node",
                node=summary,
                node_path=node.path(),
                applied_parameters=applied,
                cooked=cook,
                valid=True,
                validation_scope="parameters_and_cached_diagnostics",
                simulation_verified=False,
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure POP node")


@skill_entry
def main(**kwargs):
    return configure_pop_source(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
