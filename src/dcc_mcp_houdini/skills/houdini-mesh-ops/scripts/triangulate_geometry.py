"""Append a Divide SOP configured to triangulate (convex) polygons."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _mesh_common import get_node, make_downstream_sop, node_summary, set_parm_if_exists  # noqa: E402


def triangulate_geometry(input_path: str, node_name: Optional[str] = None) -> dict:
    """Create a Divide SOP downstream of *input_path* set to convex triangles."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, input_path)
        divide = make_downstream_sop(source, "divide", node_name)
        # Convex polygons into triangles (max 3 sides).
        set_parm_if_exists(divide, "convex", 1)
        set_parm_if_exists(divide, "numsides", 3)
        return skill_success(
            "Created triangulate (divide) SOP",
            input_path=source.path(),
            node=node_summary(divide),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create triangulate SOP")


@skill_entry
def main(**kwargs) -> dict:
    return triangulate_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
