"""Analyse a Wrangle cook failure and locate the root cause."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def diagnose_wrangle(node_path: str) -> dict:
    """Locate the failure in *node_path* by cooking and analysing the errors.

    Returns a structured diagnosis: likely cause, error location, and a
    suggested fix.  This is the post-mortem companion to :func:`cook_wrangle`.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._vex_executor import cook_and_diagnose, locate_wrangle_failure
    except ImportError as exc:
        return skill_error("VEX module not available", str(exc))

    try:
        diag = cook_and_diagnose(hou, node_path, force=True)
        analysis = locate_wrangle_failure(diag)

        return skill_success(
            f"Diagnosis: {analysis.get('likely_cause', 'unknown')}",
            **analysis,
            geometry_diagnostics=diag.to_dict(),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to diagnose Wrangle")


@skill_entry
def main(**kwargs) -> dict:
    return diagnose_wrangle(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
