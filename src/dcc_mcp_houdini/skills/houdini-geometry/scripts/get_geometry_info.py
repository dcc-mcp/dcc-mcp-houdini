"""Return point/primitive/vertex counts and bounds for a SOP node."""

from __future__ import annotations

from _geo_common import cooked_geometry, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _vec(value) -> list:
    try:
        return [float(v) for v in value]
    except TypeError:
        return [float(value[i]) for i in range(len(value))]


def _count(geometry, method_name):
    method = getattr(geometry, method_name, None)
    if not callable(method):
        return None
    try:
        return int(method())
    except Exception:  # noqa: BLE001
        return None


def get_geometry_info(node_path: str) -> dict:
    """Summarise geometry counts and bounds for *node_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        geo = cooked_geometry(node)
        context = {
            "node_path": node.path(),
            "point_count": _count(geo, "pointCount"),
            "primitive_count": _count(geo, "primCount"),
            "vertex_count": _count(geo, "vertexCount"),
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
