"""Inspect the selected Houdini node and its display SOP in one call."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_KEY_ATTRIBUTES = {
    "point": ("P", "N", "v", "Cd", "id", "name", "orient", "pivot"),
    "primitive": ("name", "path", "active", "shop_materialpath"),
    "vertex": ("uv", "N"),
    "detail": ("name", "path", "frame", "fps"),
}
_ATTRIBUTE_FINDERS = {
    "point": "findPointAttrib",
    "primitive": "findPrimAttrib",
    "vertex": "findVertexAttrib",
    "detail": "findGlobalAttrib",
}
_PACKED_TYPE_FALLBACKS = (
    "PackedFragment",
    "PackedGeometry",
    "PackedPrim",
    "PackedDisk",
    "PackedDiskSequence",
)


def _call_or_none(obj: Any, method_name: str) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:  # noqa: BLE001
        return None


def _category_name(node: Any) -> Optional[str]:
    node_type = _call_or_none(node, "type")
    category = _call_or_none(node_type, "category")
    name = _call_or_none(category, "name")
    return str(name) if name is not None else None


def _is_sop(node: Any) -> bool:
    category = _category_name(node)
    return bool(category and category.lower() == "sop")


def _node_summary(node: Any) -> Optional[Dict[str, Any]]:
    if node is None:
        return None
    node_type = _call_or_none(node, "type")
    return {
        "path": _call_or_none(node, "path"),
        "name": _call_or_none(node, "name"),
        "type": _call_or_none(node_type, "name"),
        "category": _category_name(node),
    }


def _current_node(selected: List[Any]) -> Any:
    for node in selected:
        if _call_or_none(node, "isCurrent"):
            return node
    return selected[-1] if selected else None


def _display_sop(selected: List[Any], current: Any) -> Any:
    candidates = ([current] if current is not None else []) + [node for node in selected if node is not current]
    for node in candidates:
        owner = _call_or_none(node, "parent") if _is_sop(node) else node
        display = _call_or_none(owner, "displayNode")
        if display is not None and _is_sop(display):
            return display
    for node in candidates:
        if _is_sop(node) and _call_or_none(node, "isDisplayFlagSet"):
            return node
    return current if _is_sop(current) else None


def _count(geometry: Any, method_name: str) -> Optional[int]:
    value = _call_or_none(geometry, method_name)
    return int(value) if value is not None else None


def _packed_primitive_counts(geometry: Any) -> Dict[str, int]:
    count_prim_type = getattr(geometry, "countPrimType", None)
    if not callable(count_prim_type):
        return {}

    type_names = _call_or_none(geometry, "primTypeNames")
    if type_names is None:
        type_names = _PACKED_TYPE_FALLBACKS

    counts: Dict[str, int] = {}
    for type_name in type_names:
        name = str(type_name)
        if "packed" not in name.lower():
            continue
        try:
            count = int(count_prim_type(type_name))
        except Exception:  # noqa: BLE001
            continue
        if count:
            counts[name] = count
    return counts


def _key_attribute_names(geometry: Any) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for owner, names in _KEY_ATTRIBUTES.items():
        finder = getattr(geometry, _ATTRIBUTE_FINDERS[owner], None)
        found[owner] = [name for name in names if callable(finder) and finder(name) is not None]
    return found


def _geometry_summary(node: Any) -> Optional[Dict[str, Any]]:
    if node is None:
        return None
    if _call_or_none(node, "needsToCook") is True:
        return {"needs_cook": True}
    geometry_method = getattr(node, "geometry", None)
    if not callable(geometry_method):
        return None
    geometry = geometry_method()
    if geometry is None:
        return None

    packed_by_type = _packed_primitive_counts(geometry)
    return {
        "needs_cook": False,
        "point_count": _count(geometry, "pointCount"),
        "primitive_count": _count(geometry, "primCount"),
        "vertex_count": _count(geometry, "vertexCount"),
        "packed_primitive_count": sum(packed_by_type.values()),
        "packed_primitive_counts": packed_by_type,
        "key_attributes": _key_attribute_names(geometry),
    }


def _timeline(hou: Any) -> Dict[str, Any]:
    start_frame, end_frame = hou.playbar.playbackRange()
    return {
        "frame": hou.frame(),
        "start_frame": start_frame,
        "end_frame": end_frame,
        "fps": hou.fps(),
    }


def inspect_selection() -> dict:
    """Return selection, display-SOP geometry counts, attributes, and timeline."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        selected = list(hou.selectedNodes())
        current = _current_node(selected)
        display = _display_sop(selected, current)
        return skill_success(
            "Inspected Houdini selection",
            selection=[summary for summary in (_node_summary(node) for node in selected) if summary is not None],
            current_node=_node_summary(current),
            display_node=_node_summary(display),
            geometry=_geometry_summary(display),
            timeline=_timeline(hou),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect Houdini selection")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`inspect_selection`."""
    return inspect_selection(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
