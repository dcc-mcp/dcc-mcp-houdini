"""Rename a Houdini node."""

from __future__ import annotations

from _object_common import get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def rename_node(node_path: str, new_name: str, unique_name: bool = True) -> dict:
    """Rename the node at *node_path* to *new_name*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        old_path = node.path()
        node.setName(new_name, unique_name=unique_name)
        return skill_success(
            "Renamed node",
            old_path=old_path,
            node=node_summary(node),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to rename node")


@skill_entry
def main(**kwargs) -> dict:
    return rename_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
