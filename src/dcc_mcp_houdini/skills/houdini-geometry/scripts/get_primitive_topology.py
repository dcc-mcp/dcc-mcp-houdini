"""Inspect a bounded page of ordered primitive vertex-to-point references."""

from itertools import islice

from _geo_common import cooked_geometry, get_node
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini._bounded_values import require_range


def get_primitive_topology(node_path: str, offset: int = 0, limit: int = 16, vertex_limit: int = 64) -> dict:
    try:
        import hou
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        require_range(offset, "offset", 0, 2147483647)
        require_range(limit, "limit", 1, 32)
        require_range(vertex_limit, "vertex_limit", 1, 128)
        node = get_node(hou, node_path)
        geo = cooked_geometry(node)
        total = geo.primCount()
        rows = []
        for index in range(offset, min(total, offset + limit)):
            primitive = geo.prim(index)
            if primitive is None:
                raise RuntimeError("Geometry changed during topology inspection")
            count = primitive.numVertices()
            points = [v.point().number() for v in islice(primitive.vertices(), vertex_limit)]
            closed = getattr(primitive, "isClosed", None)
            rows.append(
                {
                    "primitive_index": index,
                    "primitive_type": str(primitive.type()),
                    "vertex_count": count,
                    "point_indices": points,
                    "vertices_truncated": count > len(points),
                    "closed": bool(closed()) if callable(closed) else None,
                }
            )
        next_offset = offset + len(rows)
        return skill_success(
            "Read ordered primitive topology",
            node_path=node.path(),
            total_count=total,
            offset=offset,
            count=len(rows),
            primitives=rows,
            next_offset=next_offset if next_offset < total else None,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read primitive topology")


@skill_entry
def main(**kwargs):
    return get_primitive_topology(**kwargs)
