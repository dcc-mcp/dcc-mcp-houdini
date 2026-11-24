"""Export normalized Houdini SOP modeling state."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

SCHEMA_NAME = "dcc-mcp/model-state"
SCHEMA_VERSION = 1
CHECK_NAMES = ("parts", "hierarchy", "materials", "uv_coverage", "non_manifold", "euler")


def _call(value: Any, method: str, default: Any = None) -> Any:
    function = getattr(value, method, None)
    if not callable(function):
        return default
    try:
        return function()
    except Exception:  # noqa: BLE001
        return default


def _call_with_args(value: Any, method: str, *args: Any) -> Any:
    function = getattr(value, method, None)
    if not callable(function):
        return None
    try:
        return function(*args)
    except Exception:  # noqa: BLE001
        return None


def _vector(value: Any) -> list[float]:
    return [float(value[index]) for index in range(3)]


def _count(geometry: Any, method: str) -> Optional[int]:
    value = _call(geometry, method)
    if value is None:
        return None
    return int(value)


def _bounds(geometry: Any) -> Optional[dict[str, list[float]]]:
    bounding_box = _call(geometry, "boundingBox")
    if bounding_box is None:
        return None
    return {
        "min": _vector(bounding_box.minvec()),
        "max": _vector(bounding_box.maxvec()),
    }


def _attribute_names(geometry: Any, method: str) -> Iterable[str]:
    attributes = _call(geometry, method, []) or []
    for attribute in attributes:
        name = _call(attribute, "name")
        if name:
            yield str(name)


def _uv_sets(geometry: Any) -> int:
    names = set()
    for method in ("vertexAttribs", "pointAttribs", "primAttribs", "globalAttribs"):
        names.update(name for name in _attribute_names(geometry, method) if name.lower() == "uv")
    return len(names)


def _material_name(geometry: Any) -> Optional[str]:
    for attribute_name in ("shop_materialpath", "sop_materialpath", "material"):
        attribute = _call_with_args(geometry, "findPrimAttrib", attribute_name)
        if attribute is None:
            continue
        primitive = _call_with_args(geometry, "prim", 0)
        value = _call_with_args(primitive, "attribValue", attribute)
        if value:
            return str(value)
    return None


def _is_manifold(geometry: Any) -> Optional[bool]:
    value = _call(geometry, "isManifold")
    if value is None:
        return None
    return bool(value)


def _transform(node: Any) -> tuple[dict[str, Any], Optional[list[float]]]:
    parent = _call(node, "parent")
    transform: dict[str, Any] = {}
    parent_path = _call(parent, "path")
    if parent_path:
        transform["object_path"] = str(parent_path)
    matrix = _call(parent, "worldTransform")
    if matrix is None:
        return transform, None
    translation = _call(matrix, "extractTranslates")
    if translation is not None:
        transform["location"] = _vector(translation)
    rotation = _call(matrix, "extractRotates")
    if rotation is not None:
        euler = _vector(rotation)
        transform["rotation"] = euler
        return transform, euler
    return transform, None


def _build_state(node: Any, geometry: Any) -> dict[str, Any]:
    unavailable = set()
    partial = False
    node_path = str(node.path())
    node_name = str(node.name())
    counts = {
        "point_count": _count(geometry, "pointCount"),
        "primitive_count": _count(geometry, "primCount"),
        "vertex_count": _count(geometry, "vertexCount"),
    }
    if any(value is None for value in counts.values()):
        partial = True

    mesh = {
        "name": node_name,
        "uv_sets": _uv_sets(geometry),
        "material": _material_name(geometry),
        "is_non_manifold": False,
        "vertex_count": counts["vertex_count"] or 0,
    }
    mesh.update({key: value for key, value in counts.items() if value is not None})
    bounds = _bounds(geometry)
    if bounds is not None:
        mesh["bounds"] = bounds
    else:
        partial = True

    manifold = _is_manifold(geometry)
    if manifold is None:
        unavailable.add("non_manifold")
        partial = True
    else:
        mesh["is_non_manifold"] = not manifold

    transform, euler = _transform(node)
    object_state = {"name": node_name, "transform": transform}
    if euler is None:
        unavailable.add("euler")
        partial = True
    else:
        object_state["euler"] = euler

    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "partial": partial,
        "unavailable": sorted(unavailable),
        "parts": [node_name],
        "hierarchy": [node_path],
        "meshes": [mesh],
        "objects": [object_state],
    }


def export_model_state(node_path: str) -> dict:
    """Export bounded modeling state for one cooked SOP node."""
    try:
        import hou
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = hou.node(node_path)
        if node is None:
            return skill_error("Houdini node not found", node_path)
        geometry = node.geometry()
        if geometry is None:
            return skill_error("Node has no SOP geometry", node_path)
        state = _build_state(node, geometry)
        return skill_success(
            "Houdini modeling state exported",
            state=state,
            node_path=node.path(),
            partial=state["partial"],
        )
    except Exception as exc:  # noqa: BLE001
        return skill_exception(exc, message="Failed to export Houdini modeling state")


@skill_entry
def main(**kwargs) -> dict:
    return export_model_state(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
