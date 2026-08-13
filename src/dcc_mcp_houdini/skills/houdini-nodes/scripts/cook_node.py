"""Cook a Houdini node."""

from __future__ import annotations

from _node_common import get_node, hou_import_error, node_summary
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

from dcc_mcp_houdini.inline_cook_policy import assess_inline_cook


def _call_string_list(node, method_name: str) -> list:
    method = getattr(node, method_name, None)
    if not callable(method):
        return []
    try:
        return list(method())
    except Exception:
        return []


def cook_node(node_path: str, force: bool = False, allow_heavy_inline: bool = False) -> dict:
    """Cook a Houdini node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    node = None
    try:
        node = get_node(hou, node_path)
        rejection = None if allow_heavy_inline else assess_inline_cook(node)
        if rejection is not None:
            return skill_error(
                "Inline Houdini cook rejected by safety policy",
                "Potentially heavy SOP cook requires isolated execution",
                node=node_summary(node),
                force=force,
                **rejection,
            )
        node.cook(force=force)
        return skill_success(
            "Cooked Houdini node",
            node=node_summary(node),
            force=force,
            errors=_call_string_list(node, "errors"),
            warnings=_call_string_list(node, "warnings"),
        )
    except Exception as exc:
        result = skill_error(
            "Failed to cook Houdini node",
            "Houdini node cook failed",
            error_type=type(exc).__name__,
        )
        if node is not None:
            context = result.setdefault("context", {})
            context.update(
                node=node_summary(node),
                force=force,
                errors=_call_string_list(node, "errors"),
                warnings=_call_string_list(node, "warnings"),
            )
        return result


@skill_entry
def main(**kwargs) -> dict:
    return cook_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
