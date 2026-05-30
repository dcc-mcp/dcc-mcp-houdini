"""Create a Houdini node."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _node_common import get_node, hou_import_error, node_summary


def create_node(
    parent_path: str,
    node_type: str,
    node_name: Optional[str] = None,
    exact_type_name: bool = False,
    run_init_scripts: bool = True,
    load_contents: bool = True,
    set_current: bool = False,
) -> dict:
    """Create a node under *parent_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        parent = get_node(hou, parent_path)
        node = parent.createNode(
            node_type,
            node_name=node_name,
            run_init_scripts=run_init_scripts,
            load_contents=load_contents,
            exact_type_name=exact_type_name,
        )
        if set_current and hasattr(node, "setCurrent"):
            node.setCurrent(True, clear_all_selected=True)
        return skill_success(
            "Created Houdini node",
            parent_path=parent.path(),
            node=node_summary(node),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create Houdini node")


@skill_entry
def main(**kwargs) -> dict:
    return create_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
