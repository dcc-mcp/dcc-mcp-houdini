"""Plan a Copernicus fractal-sample + heightfield-strata terrain chain.

Pure and host-independent: this tool does not import ``hou``, touch a scene, or
cook anything. It returns a deterministic, JSON-safe authoring plan (node types,
recommended parameter names, required setup) that an agent can hand to
``build_composite_chain`` / ``create_terrain_generator`` and then cook/render.
Use it to make the fractal-sample and strata capabilities discoverable without
guessing raw Houdini node type names or parameter names.
"""

from _cop_terrain import build_terrain_plan
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def plan_fractal_terrain(generator="fractal_noise", with_strata=True, with_output=True) -> dict:
    try:
        if not isinstance(with_strata, bool) or not isinstance(with_output, bool):
            raise ValueError("with_strata and with_output must be booleans")
        plan = build_terrain_plan(generator, with_strata=with_strata, with_output=with_output)
        return skill_success(
            "Planned Copernicus fractal-sample / strata terrain chain",
            plan=plan,
            generator=plan["generator"],
            node_type=plan["node_type"],
            family=plan["family"],
            step_count=plan["step_count"],
            artifact_verified=False,
            validation_scope="plan_only_no_host_access",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to plan terrain chain", include_traceback=False)


@skill_entry
def main(**kwargs):
    return plan_fractal_terrain(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
