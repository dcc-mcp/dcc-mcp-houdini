"""Return a host-independent authoring plan for a modern Houdini node family.

Pure and read-only: this tool never imports ``hou``, touches a scene, or cooks.
It exposes the four feature families (RBD material fracture, COps pyro, sparse
GPU pyro, rasterize Volume) as a deterministic, JSON-safe plan -- real node
types, parent categories, recommended parameter names and required setup --
so an agent can author the nodes with ``create_modern_sim_node`` without
guessing version-sensitive Houdini node type names.

The plan is guidance only. It never claims a cooked simulation or rendered
artifact (``artifact_verified``/``simulation_verified`` are always false).
"""

from _modern_sim import FAMILIES, aliases_for_family, build_modern_sim_plan
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def plan_modern_simulation(family=None) -> dict:
    try:
        if family is not None and not isinstance(family, str):
            raise ValueError("family must be a string when provided")
        if family is None:
            return skill_success(
                "Listed modern Houdini simulation feature families",
                families=list(FAMILIES),
                family_count=len(FAMILIES),
                aliases={name: list(aliases_for_family(name)) for name in FAMILIES},
                validation_scope="catalog_only_no_host_access",
                artifact_verified=False,
                simulation_verified=False,
            )
        plan = build_modern_sim_plan(family)
        return skill_success(
            "Planned modern Houdini simulation node chain",
            plan=plan,
            family=plan["family"],
            aliases=plan["aliases"],
            step_count=plan["step_count"],
            validation_scope=plan["validation_scope"],
            artifact_verified=False,
            simulation_verified=False,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to plan modern simulation", include_traceback=False)


@skill_entry
def main(**kwargs):
    return plan_modern_simulation(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
