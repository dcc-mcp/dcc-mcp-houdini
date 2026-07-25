"""Create a typed Wrangle SOP node with optional validated VEX snippet."""

from __future__ import annotations

from typing import Any, Dict, Optional

from _vex_common import resolve_vex_context, resolve_wrangle_type  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_wrangle(
    parent_path: str,
    wrangle_type: str = "attribwrangle",
    node_name: Optional[str] = None,
    run_over: str = "points",
    vex_code: Optional[str] = None,
    bindings: Optional[Dict[str, str]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    set_display: bool = False,
    set_render: bool = False,
) -> dict:
    """Create a Wrangle SOP node under *parent_path*.

    If *vex_code* is provided, it is validated client-side BEFORE being
    committed to the node.  This is NOT a Python execution path.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._vex_types import VexSnippet, WrangleNodeSpec
        from dcc_mcp_houdini._vex_executor import create_wrangle as _create
        from dcc_mcp_houdini._vex_validator import validate_vex_snippet_client
    except ImportError as exc:
        return skill_error("VEX module not available", str(exc))

    # ── Build snippet if VEX code provided ─────────────────────────────
    snippet = None
    if vex_code:
        client_errors = validate_vex_snippet_client(vex_code)
        if client_errors:
            return skill_error(
                "VEX snippet validation failed",
                f"{len(client_errors)} validation error(s) found",
                validation_errors=[e.to_dict() for e in client_errors],
                hint="Fix the reported errors and retry.  Only standard VEX builtins and constructs are permitted.",
            )
        try:
            snippet = VexSnippet(
                code=vex_code,
                context=resolve_vex_context(run_over),
                bindings=bindings or {},
                parameter_values=parameters or {},
            )
        except ValueError as exc:
            return skill_error("Invalid VEX snippet", f"VexSnippet construction failed: {exc}")

    spec = WrangleNodeSpec(
        parent_path=parent_path,
        node_name=node_name,
        wrangle_type=resolve_wrangle_type(wrangle_type),
        run_over=resolve_vex_context(run_over),
        snippet=snippet,
        set_display=set_display,
        set_render=set_render,
    )

    result = _create(hou, spec)
    if result.get("success"):
        return skill_success("Created Wrangle node", **result)
    return skill_error("Failed to create Wrangle node", **result)


@skill_entry
def main(**kwargs) -> dict:
    return create_wrangle(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
