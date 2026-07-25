"""Update VEX snippet on an existing Wrangle node (validated, no raw-string passthrough)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from _vex_common import resolve_vex_context  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def update_vex_snippet(
    node_path: str,
    vex_code: str,
    run_over: Optional[str] = None,
    bindings: Optional[Dict[str, str]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update the VEX snippet on *node_path*.

    The snippet is validated client-side before being committed.  The
    previous snippet (first 200 chars) is preserved in the result for
    audit trail purposes.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._vex_types import VexContext, VexSnippet
        from dcc_mcp_houdini._vex_executor import update_vex_snippet as _update
        from dcc_mcp_houdini._vex_validator import validate_vex_snippet_client
    except ImportError as exc:
        return skill_error("VEX module not available", str(exc))

    # ── Client-side validation ─────────────────────────────────────────
    client_errors = validate_vex_snippet_client(vex_code)
    if client_errors:
        return skill_error(
            "VEX snippet validation failed",
            f"{len(client_errors)} validation error(s) found",
            validation_errors=[e.to_dict() for e in client_errors],
            hint="Fix the reported errors and retry.",
        )

    context = resolve_vex_context(run_over) if run_over else VexContext.POINTS

    try:
        snippet = VexSnippet(
            code=vex_code,
            context=context,
            bindings=bindings or {},
            parameter_values=parameters or {},
        )
    except ValueError as exc:
        return skill_error("Invalid VEX snippet", str(exc))

    result = _update(hou, node_path, snippet)
    if result.get("success"):
        return skill_success("Updated VEX snippet", **result)
    return skill_error("Failed to update VEX snippet", **result)


@skill_entry
def main(**kwargs) -> dict:
    return update_vex_snippet(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
