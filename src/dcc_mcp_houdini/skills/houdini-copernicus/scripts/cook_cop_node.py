"""Cook a Copernicus node and report cached diagnostics without claiming an artifact."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary


def cook_cop_node(node_path: str, force: bool = True) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(force, bool):
            raise ValueError("force must be boolean")
        node = get_node(hou, node_path)
        cooked = True
        cook_error = None
        try:
            node.cook(force=force)
        except Exception as exc:
            cooked = False
            cook_error = str(exc)
        summary = node_summary(node)
        errors = list(summary["errors"])
        warnings = list(summary["warnings"])
        if cook_error is not None:
            errors.append("Cook failed: {}".format(cook_error))
        return skill_success(
            "Cooked Cop node",
            node=summary,
            node_path=node.path(),
            cooked=cooked,
            forced=force,
            valid=cooked and not errors,
            errors=errors,
            warnings=warnings,
            validation_scope="cook_and_cached_diagnostics",
            artifact_verified=False,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to cook Cop node")


@skill_entry
def main(**kwargs):
    return cook_cop_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
