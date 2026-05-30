"""Shared helpers for Houdini render/viewport skills."""

from __future__ import annotations

import os
from typing import Any, Optional, Sequence

MAX_DIMENSION = 4096


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def scene_viewer(hou):
    """Return the current Scene Viewer pane tab or None."""
    try:
        return hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    except Exception:  # noqa: BLE001
        return None


def clamp_resolution(resolution: Optional[Sequence[int]]) -> Optional[list]:
    """Clamp [w, h] to a sane maximum; return None when not provided."""
    if not resolution or len(resolution) < 2:
        return None
    width = max(1, min(int(resolution[0]), MAX_DIMENSION))
    height = max(1, min(int(resolution[1]), MAX_DIMENSION))
    return [width, height]


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


def eval_first_parm(node: Any, names: Sequence[str]):
    """Eval the first existing parm/parm-tuple in *names*, else None."""
    for name in names:
        parm_tuple = node.parmTuple(name)
        if parm_tuple is not None:
            try:
                return [v for v in parm_tuple.eval()]
            except Exception:  # noqa: BLE001
                continue
        parm = node.parm(name)
        if parm is not None:
            try:
                return parm.eval()
            except Exception:  # noqa: BLE001
                continue
    return None


def apply_frame_range(node: Any, frame_range: Optional[Sequence[float]]) -> Optional[list]:
    """Set ROP frame-range parms defensively. Return the applied [start, end]."""
    if not frame_range:
        return None
    start, end = float(frame_range[0]), float(frame_range[1])
    step = float(frame_range[2]) if len(frame_range) > 2 else 1.0
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


def existing_outputs(output_path: str) -> list:
    """Return [output_path] when it is an existing file, else []."""
    return [output_path] if output_path and os.path.isfile(output_path) else []
