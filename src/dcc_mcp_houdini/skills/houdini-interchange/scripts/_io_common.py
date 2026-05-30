"""Shared helpers for Houdini interchange (import/export) skills."""

from __future__ import annotations

import os
from typing import Any, Optional, Sequence

# Suffix -> coarse format category.
_FORMAT_BY_SUFFIX = {
    ".bgeo": "geometry",
    ".geo": "geometry",
    ".bgeo.sc": "geometry",
    ".ply": "geometry",
    ".obj": "obj",
    ".fbx": "fbx",
    ".abc": "alembic",
    ".usd": "usd",
    ".usda": "usd",
    ".usdc": "usd",
    ".usdz": "usd",
}

# Formats a Houdini `file` SOP can read directly.
_IMPORTABLE = {"geometry", "obj", "fbx", "alembic", "usd"}


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def detect_format(file_path: str) -> str:
    """Return a coarse format category for *file_path* based on its suffix."""
    lowered = file_path.lower()
    for suffix, category in sorted(_FORMAT_BY_SUFFIX.items(), key=lambda kv: -len(kv[0])):
        if lowered.endswith(suffix):
            return category
    return "unknown"


def probe(file_path: str) -> dict:
    """Return a structured probe of a file path (no Houdini required)."""
    fmt = detect_format(file_path)
    exists = os.path.isfile(file_path)
    info = {
        "file_path": file_path,
        "exists": exists,
        "format": fmt,
        "is_supported_import": fmt in _IMPORTABLE,
    }
    if exists:
        try:
            info["size_bytes"] = os.path.getsize(file_path)
        except OSError:
            info["size_bytes"] = None
    return info


def ensure_parent_dir(file_path: str) -> None:
    """Create the parent directory of *file_path* when missing."""
    parent = os.path.dirname(os.path.abspath(file_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def set_parm_if_exists(node: Any, name: str, value: Any) -> bool:
    """Set a scalar/tuple parm only when it exists. Return whether it was set."""
    if isinstance(value, (list, tuple)):
        parm_tuple = node.parmTuple(name)
        if parm_tuple is None:
            return False
        parm_tuple.set(tuple(value))
        return True
    parm = node.parm(name)
    if parm is None:
        return False
    parm.set(value)
    return True


def set_first_parm(node: Any, names: Sequence[str], value: Any) -> Optional[str]:
    """Set the first existing parm in *names*; return the name used or None."""
    for name in names:
        if set_parm_if_exists(node, name, value):
            return name
    return None


def apply_frame_range(node: Any, frame_range: Optional[Sequence[float]]) -> Optional[list]:
    """Set ROP frame-range parms defensively. Return the applied [start, end]."""
    if not frame_range:
        return None
    start, end = float(frame_range[0]), float(frame_range[1])
    step = float(frame_range[2]) if len(frame_range) > 2 else 1.0
    # trange=1 -> "Render Frame Range".
    set_parm_if_exists(node, "trange", 1)
    if not set_parm_if_exists(node, "f", [start, end, step]):
        set_parm_if_exists(node, "f1", start)
        set_parm_if_exists(node, "f2", end)
        set_parm_if_exists(node, "f3", step)
    return [start, end]


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }
