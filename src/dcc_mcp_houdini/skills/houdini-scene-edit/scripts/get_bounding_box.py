"""Return the geometry bounding box of a Houdini node."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _scene_edit_common import get_node, vec_to_list  # noqa: E402


def _resolve_geometry(node):
    """Return geometry for a SOP node or an OBJ geo's display node."""
    geo = None
    if hasattr(node, "geometry"):
        geo = node.geometry()
    if geo is None and hasattr(node, "displayNode"):
        display = node.displayNode()
        if display is not None and hasattr(display, "geometry"):
            geo = display.geometry()
    return geo


def get_bounding_box(node_path: str) -> dict:
    """Compute the world/local bounding box of *node_path*'s geometry."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        geo = _resolve_geometry(node)
        if geo is None:
            return skill_error(
                "No geometry to measure",
                "Node has no cookable geometry: {}".format(node_path),
                possible_solutions=[
                    "Point at a SOP node or an OBJ geo with a display node",
                ],
            )
        bbox = geo.boundingBox()
        return skill_success(
            "Computed bounding box",
            node_path=node.path(),
            min=vec_to_list(bbox.minvec()),
            max=vec_to_list(bbox.maxvec()),
            size=vec_to_list(bbox.sizevec()),
            center=vec_to_list(bbox.center()),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to compute bounding box")


@skill_entry
def main(**kwargs) -> dict:
    return get_bounding_box(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
