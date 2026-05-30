"""Replace the current Houdini node selection."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _scene_edit_common import node_summary  # noqa: E402


def set_selection(node_paths: List[str], clear_existing: bool = True) -> dict:
    """Select the nodes at *node_paths*.

    When ``clear_existing`` is ``True`` the previous selection is cleared
    first. Unknown paths are reported in ``missing`` without aborting.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if clear_existing:
            hou.clearAllSelected()
        selected = []
        missing = []
        for path in node_paths:
            node = hou.node(path)
            if node is None:
                missing.append(path)
                continue
            node.setSelected(True)
            selected.append(node_summary(node))
        if not selected and missing:
            return skill_error(
                "No nodes selected",
                "None of the requested paths exist",
                missing=missing,
            )
        return skill_success(
            "Updated selection",
            selected=selected,
            count=len(selected),
            missing=missing,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set selection")


@skill_entry
def main(**kwargs) -> dict:
    return set_selection(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
