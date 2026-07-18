"""Delete a Houdini node."""

from __future__ import annotations

from _node_common import get_node, hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def delete_node(node_path: str) -> dict:
    """Destroy a Houdini node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        node = get_node(hou, node_path)
        path = node.path()
        node.destroy()
        return skill_success("Deleted Houdini node", node_path=path)
    except Exception as exc:
        return skill_exception(exc, message="Failed to delete Houdini node")


@skill_entry
def main(**kwargs) -> dict:
    return delete_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
