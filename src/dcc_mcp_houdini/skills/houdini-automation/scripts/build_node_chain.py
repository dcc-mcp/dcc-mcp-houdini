"""Build a small Houdini node chain from structured specs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _automation_common import hou_import_error, node_summary, set_parm_value


def _resolve_created(parent, created: Dict[str, Any], ref: str):
    if ref in created:
        return created[ref]
    node = parent.node(ref)
    if node is not None:
        return node
    return None


def build_node_chain(
    parent_path: str,
    nodes: List[Dict[str, Any]],
    connections: Optional[List[Dict[str, Any]]] = None,
    layout: bool = True,
    cook_last: bool = True,
) -> dict:
    """Create nodes, wire them, layout, and optionally cook the last node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        parent = hou.node(parent_path)
        if parent is None:
            raise ValueError("Parent node not found: {}".format(parent_path))

        created: Dict[str, Any] = {}
        ordered = []
        for spec in nodes:
            node_type = spec["node_type"]
            node_name = spec.get("node_name")
            node = parent.createNode(node_type, node_name=node_name)
            for parm_name, value in (spec.get("parameters") or {}).items():
                set_parm_value(node, parm_name, value)
            created[node.name()] = node
            created[node.path()] = node
            ordered.append(node)

        for conn in connections or []:
            input_node = _resolve_created(parent, created, conn["input"])
            output_node = _resolve_created(parent, created, conn["output"])
            if input_node is None or output_node is None:
                raise ValueError("Connection references unknown node: {}".format(conn))
            input_node.setInput(
                int(conn.get("input_index", 0)),
                output_node,
                int(conn.get("output_index", 0)),
            )

        if layout:
            parent.layoutChildren()
        cooked = None
        if cook_last and ordered:
            cooked = ordered[-1]
            cooked.cook(force=False)

        return skill_success(
            "Built Houdini node chain",
            parent_path=parent.path(),
            nodes=[node_summary(node) for node in ordered],
            cooked_node=node_summary(cooked) if cooked is not None else None,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to build Houdini node chain")


@skill_entry
def main(**kwargs) -> dict:
    return build_node_chain(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
