"""Move a Houdini node into a different parent network."""

from __future__ import annotations

from _object_common import get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def parent_node(node_path: str, new_parent_path: str) -> dict:
    """Reparent *node_path* under *new_parent_path* using ``hou.moveNodesTo``."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        new_parent = get_node(hou, new_parent_path)
        moved = hou.moveNodesTo([node], new_parent)
        result_node = moved[0] if moved else None
        summary = node_summary(result_node) if result_node is not None else None
        return skill_success(
            "Reparented node",
            new_parent_path=new_parent.path(),
            node=summary,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to reparent node")


@skill_entry
def main(**kwargs) -> dict:
    return parent_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
