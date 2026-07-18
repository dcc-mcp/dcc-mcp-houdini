"""Duplicate a Houdini node within its parent network."""

from __future__ import annotations

from typing import Optional

from _object_common import get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def duplicate_node(node_path: str, new_name: Optional[str] = None) -> dict:
    """Copy the node at *node_path* into its parent and optionally rename it."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parent = node.parent()
        if parent is None:
            return skill_error("Cannot duplicate", "Node has no parent network")
        copies = parent.copyItems([node])
        if not copies:
            return skill_error("Duplicate failed", "Houdini returned no copied items")
        new_node = copies[0]
        if new_name:
            new_node.setName(new_name, unique_name=True)
        return skill_success(
            "Duplicated node",
            source_path=node.path(),
            node=node_summary(new_node),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to duplicate node")


@skill_entry
def main(**kwargs) -> dict:
    return duplicate_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
