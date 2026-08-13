"""Cook a SOP node and report errors/warnings."""

from __future__ import annotations

from _geo_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

from dcc_mcp_houdini.inline_cook_policy import assess_inline_cook, public_exception_message


def get_cook_status(node_path: str, force: bool = False, allow_heavy_inline: bool = False) -> dict:
    """Cook *node_path* and return any cook errors and warnings."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        rejection = None if allow_heavy_inline else assess_inline_cook(node)
        if rejection is not None:
            return skill_error(
                "Inline Houdini cook rejected by safety policy",
                "Potentially heavy SOP cook requires isolated execution",
                node_path=node.path(),
                **rejection,
            )
        cook_error = None
        try:
            node.cook(force=force)
        except Exception as exc:  # noqa: BLE001 - redact host paths from the public result
            cook_error = public_exception_message(exc)
        errors = list(node.errors()) if hasattr(node, "errors") else []
        warnings = list(node.warnings()) if hasattr(node, "warnings") else []
        return skill_success(
            "Cooked node",
            node_path=node.path(),
            cooked=cook_error is None,
            cook_error=cook_error,
            errors=errors,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_error("Failed to cook node", "Houdini node cook failed", error_type=type(exc).__name__)


@skill_entry
def main(**kwargs) -> dict:
    return get_cook_status(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
