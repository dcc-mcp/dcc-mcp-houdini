"""Cook a TOP/PDG node and report work-item results."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_auto_common import get_node, node_summary  # noqa: E402


def cook_top_network(node_path: str, block: bool = True) -> dict:
    """Cook the TOP node at *node_path* (PDG), optionally blocking until done."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        cook_fn = getattr(node, "cookWorkItems", None)
        if not callable(cook_fn):
            return skill_error(
                "Not a TOP node",
                "Node has no cookWorkItems(); expected a TOP/PDG node",
                node=node_summary(node),
            )
        try:
            cook_fn(block=block)
        except TypeError:
            cook_fn()

        summary = {"node": node_summary(node), "blocked": bool(block)}
        # Best-effort work-item statistics via the PDG graph context.
        try:
            context = node.getPDGGraphContext()
            graph = context.graph if context is not None else None
            if graph is not None:
                items = list(graph.workItems()) if hasattr(graph, "workItems") else []
                summary["work_item_count"] = len(items)
        except Exception:  # noqa: BLE001
            summary["work_item_count"] = None

        errors = list(node.errors()) if hasattr(node, "errors") else []
        summary["errors"] = errors
        return skill_success(
            "Cooked TOP network" if not errors else "TOP network cooked with errors",
            **summary,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to cook TOP network")


@skill_entry
def main(**kwargs) -> dict:
    return cook_top_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
