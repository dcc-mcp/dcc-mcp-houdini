"""Cook a Houdini node."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _node_common import get_node, hou_import_error, node_summary


def _call_string_list(node, method_name: str) -> list:
    method = getattr(node, method_name, None)
    if not callable(method):
        return []
    try:
        return list(method())
    except Exception:
        return []


def cook_node(node_path: str, force: bool = False) -> dict:
    """Cook a Houdini node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        node = get_node(hou, node_path)
        node.cook(force=force)
        return skill_success(
            "Cooked Houdini node",
            node=node_summary(node),
            force=force,
            errors=_call_string_list(node, "errors"),
            warnings=_call_string_list(node, "warnings"),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to cook Houdini node")


@skill_entry
def main(**kwargs) -> dict:
    return cook_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
