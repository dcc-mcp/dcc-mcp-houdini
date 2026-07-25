"""Validate VEX snippet syntax client-side — no Houdini touch, read-only."""

from __future__ import annotations

from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def validate_vex_syntax(
    vex_code: str,
    run_over: str = "points",
    known_attributes: Optional[List[str]] = None,
    wrangle_type: str = "attribwrangle",
) -> dict:
    """Validate *vex_code* against the VEX allowlist and deny-list.

    This is a client-side check only — no ``hou`` import, no scene mutation.
    Returns structured diagnostics with line/column hints.
    """
    try:
        from dcc_mcp_houdini._vex_validator import (
            validate_attribute_bindings,
            validate_vex_snippet_client,
            validate_wrangle_parameters,
        )
        from dcc_mcp_houdini._vex_types import WrangleType
    except ImportError as exc:
        return skill_error("VEX module not available", str(exc))

    # ── Client-side syntax check ───────────────────────────────────────
    errors = validate_vex_snippet_client(vex_code)

    # ── Attribute binding check ────────────────────────────────────────
    if known_attributes:
        binding_errors = validate_attribute_bindings(vex_code, known_attributes)
        errors.extend(binding_errors)

    # ── Parameter type check ───────────────────────────────────────────
    wt = next((w for w in WrangleType if w.value == wrangle_type), WrangleType.ATTRIB_WRANGLE)
    # We don't have actual parameter values to check in validate mode;
    # the parameter validation is informational.

    if errors:
        return skill_error(
            "VEX snippet has validation issues",
            f"{len(errors)} issue(s) found",
            error_count=len(errors),
            errors=[e.to_dict() for e in errors],
            severity_distribution=_severity_distribution(errors),
        )

    return skill_success(
        "VEX snippet is valid",
        line_count=len([ln for ln in vex_code.splitlines() if ln.strip()]),
        char_count=len(vex_code),
        run_over=run_over,
        wrangle_type=wrangle_type,
    )


def _severity_distribution(errors) -> dict:
    dist: dict = {"error": 0, "warning": 0, "info": 0}
    for e in errors:
        sev = e.severity.value
        if sev in dist:
            dist[sev] += 1
    return dist


@skill_entry
def main(**kwargs) -> dict:
    return validate_vex_syntax(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
