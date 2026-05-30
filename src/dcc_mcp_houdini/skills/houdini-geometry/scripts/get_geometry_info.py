"""Return point/primitive/vertex counts and bounds for a SOP node."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _geo_common import cooked_geometry, get_node  # noqa: E402


def _vec(value) -> list:
    try:
        return [float(v) for v in value]
    except TypeError:
        return [float(value[i]) for i in range(len(value))]


def get_geometry_info(node_path: str) -> dict:
    """Summarise geometry counts and bounds for *node_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        geo = cooked_geometry(node)
        point_count = len(geo.points()) if hasattr(geo, "points") else None
        prim_count = len(geo.prims()) if hasattr(geo, "prims") else None
        vertex_count = None
        if hasattr(geo, "iterVertices"):
            try:
                vertex_count = sum(1 for _ in geo.iterVertices())
            except Exception:  # noqa: BLE001
                vertex_count = None
        context = {
            "node_path": node.path(),
            "point_count": point_count,
            "primitive_count": prim_count,
            "vertex_count": vertex_count,
        }
        try:
            bbox = geo.boundingBox()
            context["bounds_min"] = _vec(bbox.minvec())
            context["bounds_max"] = _vec(bbox.maxvec())
            context["bounds_size"] = _vec(bbox.sizevec())
        except Exception:  # noqa: BLE001
            pass
        return skill_success("Read geometry info", **context)
    except Exception as exc:
        return skill_exception(exc, message="Failed to read geometry info")


@skill_entry
def main(**kwargs) -> dict:
    return get_geometry_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
