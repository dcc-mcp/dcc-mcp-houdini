"""Shared helpers for Houdini render/viewport skills."""

from __future__ import annotations

import glob
import os
import re
from typing import Any, Optional, Sequence

MAX_DIMENSION = 4096
PRIMARY_OUTPUT_PARMS = ("picture", "vm_picture", "outputimage", "lopoutput", "sopoutput", "filename")


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


def eval_first_parm(node: Any, names: Sequence[str], preserve_string: bool = False):
    """Eval the first existing parm/parm-tuple in *names*, else None."""
    return eval_first_parm_named(node, names, preserve_string=preserve_string)[1]


def eval_first_parm_named(node: Any, names: Sequence[str], preserve_string: bool = False):
    """Return ``(name, value)`` for the first evaluable parameter."""
    for name in names:
        parm = node.parm(name)
        if preserve_string and parm is not None:
            try:
                return name, parm.unexpandedString()
            except Exception:  # noqa: BLE001
                continue
        parm_tuple = node.parmTuple(name)
        if parm_tuple is not None:
            try:
                return name, list(parm_tuple.eval())
            except Exception:  # noqa: BLE001
                continue
        if parm is not None:
            try:
                return name, parm.eval()
            except Exception:  # noqa: BLE001
                continue
    return None, None


def apply_frame_range(node: Any, frame_range: Optional[Sequence[float]]) -> Optional[list]:
    """Set ROP frame-range parms defensively. Return the applied [start, end]."""
    if not frame_range:
        return None
    start, end = float(frame_range[0]), float(frame_range[1])
    step = float(frame_range[2]) if len(frame_range) > 2 else 1.0
    trange = node.parm("trange")
    if trange is not None:
        trange.deleteAllKeyframes()
        trange.set(1)
    frame_tuple = node.parmTuple("f")
    if frame_tuple is not None:
        for parm, value in zip(frame_tuple, (start, end, step)):
            parm.deleteAllKeyframes()
            parm.set(value)
    else:
        for name, value in zip(("f1", "f2", "f3"), (start, end, step)):
            parm = node.parm(name)
            if parm is not None:
                parm.deleteAllKeyframes()
                parm.set(value)
    return [start, end]


def render_node(
    node: Any,
    frame_range: Optional[Sequence[float]] = None,
    ignore_inputs: bool = False,
) -> tuple:
    """Execute a render using the host contract for the node type."""
    applied_range = apply_frame_range(node, frame_range)
    type_name = node.type().name().split("::", 1)[0]
    if type_name == "usdrender_rop" and not ignore_inputs:
        execute = node.parm("execute")
        if execute is None:
            raise ValueError("Solaris USD Render node has no execute button")
        execute.pressButton()
        return applied_range, "execute"

    render = getattr(node, "render", None)
    if not callable(render):
        raise ValueError("Node has no render(); expected a ROP/output driver")
    kwargs = {}
    if frame_range:
        kwargs["frame_range"] = (
            float(frame_range[0]),
            float(frame_range[1]),
            float(frame_range[2]) if len(frame_range) > 2 else 1.0,
        )
    if ignore_inputs:
        kwargs["ignore_inputs"] = True
    try:
        render(verbose=False, **kwargs)
    except TypeError:
        render(**kwargs)
    return applied_range, "render"


def expanded_outputs(pattern: Optional[str]) -> list:
    """Return existing files matching a Houdini frame-token output pattern."""
    if not pattern:
        return []
    globbed = re.sub(r"\$F\d*", "*", pattern)
    if "*" in globbed:
        return sorted(glob.glob(globbed))
    return [pattern] if os.path.isfile(pattern) else []


def expand_output_variables(hou: Any, pattern: Optional[str]) -> Optional[str]:
    """Expand Houdini variables while preserving frame tokens for discovery."""
    if not pattern:
        return pattern
    tokens = {}

    def protect_frame_token(match: re.Match) -> str:
        placeholder = "__DCC_MCP_FRAME_TOKEN_{}__".format(len(tokens))
        tokens[placeholder] = match.group(0)
        return placeholder

    protected = re.sub(r"\$F\d*", protect_frame_token, pattern)
    expanded = hou.text.expandString(protected)
    for placeholder, token in tokens.items():
        expanded = expanded.replace(placeholder, token)
    return expanded


def requested_outputs(hou: Any, pattern: Optional[str], frame_range: Optional[Sequence[float]]) -> list:
    """Expand the output paths for the exact requested frame range."""
    if not pattern:
        return []
    if not frame_range:
        return expanded_outputs(pattern)
    start, end = float(frame_range[0]), float(frame_range[1])
    step = float(frame_range[2]) if len(frame_range) > 2 else 1.0
    if step == 0 or (end - start) * step < 0:
        raise ValueError("frame_range step must move from start toward end")
    frame = start
    tolerance = abs(step) * 1e-9
    outputs = []
    while (step > 0 and frame <= end + tolerance) or (step < 0 and frame >= end - tolerance):
        outputs.append(hou.text.expandStringAtFrame(pattern, frame))
        frame += step
    return list(dict.fromkeys(outputs))


def output_snapshot(paths: Sequence[str]) -> dict:
    """Return JSON-safe file signatures for existing output paths."""
    snapshot = {}
    for output in paths:
        try:
            stat = os.stat(output)
        except OSError:
            continue
        if os.path.isfile(output):
            snapshot[output] = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
    return snapshot


def updated_outputs(paths: Sequence[str], before: dict) -> list:
    """Return outputs created or updated since *before*."""
    current = output_snapshot(paths)
    return sorted(output for output, signature in current.items() if signature != before.get(output))


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
