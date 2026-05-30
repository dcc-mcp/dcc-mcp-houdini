"""Shared helpers for Houdini geometry-inspection skills."""

from __future__ import annotations

from typing import Any


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def cooked_geometry(node: Any) -> Any:
    """Return the node's geometry, cooking on demand. Raises when unavailable."""
    geo = node.geometry() if hasattr(node, "geometry") else None
    if geo is None:
        raise ValueError("Node has no SOP geometry: {}".format(node.path()))
    return geo


def attrib_entries(attribs) -> list:
    """Summarise a sequence of HOM attributes as name/type/size dicts."""
    entries = []
    for attrib in attribs:
        entry = {"name": _safe(attrib, "name")}
        data_type = getattr(attrib, "dataType", None)
        if callable(data_type):
            try:
                entry["data_type"] = str(attrib.dataType())
            except Exception:  # noqa: BLE001
                entry["data_type"] = None
        size = getattr(attrib, "size", None)
        if callable(size):
            try:
                entry["size"] = int(attrib.size())
            except Exception:  # noqa: BLE001
                entry["size"] = None
        entries.append(entry)
    return entries


def group_entries(groups, counter: str) -> list:
    """Summarise a sequence of HOM groups as name/count dicts.

    ``counter`` is the membership accessor for the group class
    (``"points"`` / ``"prims"`` / ``"edges"``).
    """
    entries = []
    for group in groups:
        entry = {"name": _safe(group, "name"), "count": None}
        fn = getattr(group, counter, None)
        if callable(fn):
            try:
                entry["count"] = len(fn())
            except Exception:  # noqa: BLE001
                entry["count"] = None
        entries.append(entry)
    return entries


def _safe(obj: Any, method: str):
    fn = getattr(obj, method, None)
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None
