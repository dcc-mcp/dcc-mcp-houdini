"""Layout children in a Houdini network."""

from __future__ import annotations

from _node_common import get_node, hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def layout_children(parent_path: str = "/obj", selected_only: bool = False) -> dict:
    """Layout all children or only the selected children under *parent_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        parent = get_node(hou, parent_path)
        children = list(parent.children())
        items = [node for node in hou.selectedNodes() if node.parent() == parent] if selected_only else children
        if selected_only:
            parent.layoutChildren(items=items)
        else:
            parent.layoutChildren()
        return skill_success(
            "Laid out Houdini node children",
            parent_path=parent.path(),
            child_count=len(items),
            selected_only=selected_only,
            node_paths=[node.path() for node in items],
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to layout Houdini node children")


@skill_entry
def main(**kwargs) -> dict:
    return layout_children(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
