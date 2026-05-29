"""Find Houdini nodes by name pattern and/or node type."""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _scene_edit_common import get_node, iter_nodes, node_summary  # noqa: E402


def find_nodes(
    name_pattern: Optional[str] = None,
    type_filter: Optional[str] = None,
    root_path: str = "/obj",
    recursive: bool = True,
    max_results: int = 200,
) -> dict:
    """Search under *root_path* for nodes matching the given criteria.

    ``name_pattern`` is a glob (``fnmatch``) on the node name; ``type_filter``
    is a case-insensitive substring of the node type name. At least one of the
    two should be provided to be useful, but neither is required.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        root = get_node(hou, root_path)
        matches = []
        for node in iter_nodes(root, recursive):
            if name_pattern and not fnmatch.fnmatch(node.name(), name_pattern):
                continue
            type_name = node.type().name()
            if type_filter and type_filter.lower() not in type_name.lower():
                continue
            matches.append(node_summary(node))
            if len(matches) >= max_results:
                break
        return skill_success(
            "Found matching nodes",
            nodes=matches,
            count=len(matches),
            truncated=len(matches) >= max_results,
            root_path=root_path,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to find nodes")


@skill_entry
def main(**kwargs) -> dict:
    return find_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
