"""Shared helpers for Houdini HDA automation / PDG-ROP skills."""

from __future__ import annotations

from typing import Any, Optional


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def _categories(hou: Any) -> list:
    """Return the common node-type categories to search, defensively."""
    getters = (
        "objNodeTypeCategory",
        "sopNodeTypeCategory",
        "dopNodeTypeCategory",
        "ropNodeTypeCategory",
        "topNodeTypeCategory",
        "lopNodeTypeCategory",
        "vopNodeTypeCategory",
        "cop2NodeTypeCategory",
        "chopNodeTypeCategory",
    )
    categories = []
    for name in getters:
        fn = getattr(hou, name, None)
        if callable(fn):
            try:
                categories.append(fn())
            except Exception:  # noqa: BLE001
                continue
    return categories


def find_node_type(hou: Any, type_name: str) -> Optional[Any]:
    """Find a node type by name across common categories."""
    for category in _categories(hou):
        try:
            node_type = hou.nodeType(category, type_name)
        except Exception:  # noqa: BLE001
            node_type = None
        if node_type is not None:
            return node_type
    return None


def definition_summary(definition: Any) -> dict:
    """Summarise a hou.HDADefinition into JSON-safe fields (defensive)."""
    summary: dict = {}

    def _call(attr):
        fn = getattr(definition, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                return None
        return None

    node_type = _call("nodeType")
    if node_type is not None:
        try:
            summary["node_type_name"] = node_type.name()
        except Exception:  # noqa: BLE001
            summary["node_type_name"] = None
        try:
            summary["category"] = node_type.category().name()
        except Exception:  # noqa: BLE001
            summary["category"] = None
    summary["node_type_name"] = summary.get("node_type_name") or _call("nodeTypeName")
    summary["library_path"] = _call("libraryFilePath")
    summary["version"] = _call("version")
    summary["description"] = _call("description")
    summary["is_current"] = _call("isCurrent")
    summary["is_installed"] = _call("isInstalled")
    sections = _call("sections")
    if isinstance(sections, dict):
        summary["sections"] = sorted(sections.keys())
    return summary


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }
