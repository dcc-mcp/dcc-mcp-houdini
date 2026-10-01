"""Shared helpers for Houdini render/viewport skills."""

from __future__ import annotations

import glob
import math
import os
import re
from typing import Any, Optional, Sequence

MAX_DIMENSION = 4096
RESOLUTION_X_PARMS = ("res_overridex", "resx", "vm_resx", "res1")
RESOLUTION_Y_PARMS = ("res_overridey", "resy", "vm_resy", "res2")
MANTRA_SPECIFIC_RESOLUTION = "specific"
PRIMARY_OUTPUT_PARMS = (
    "picture",
    "vm_picture",
    "outputimage",
    "copoutput",
    "lopoutput",
    "sopoutput",
    "filename",
)


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


def _resolution_scalar(node, names):
    # Houdini also exposes one-component ParmTuples for scalar controls.
    # Read the scalar directly: [0] is truthy and ["specific"] is not a token.
    for name in names:
        parm = node.parm(name)
        if parm is not None:
            try:
                return parm.eval()
            except Exception:  # noqa: BLE001
                continue
    return None


def _resolution_pair(node, tuple_names, x_names, y_names):
    values = eval_first_parm(node, tuple_names)
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        values = [_resolution_scalar(node, x_names), _resolution_scalar(node, y_names)]
    try:
        numbers = [float(value) for value in values]
        if any(not math.isfinite(value) or value < 1 or int(value) != value for value in numbers):
            return None
        return [int(value) for value in numbers]
    except (TypeError, ValueError, OverflowError):
        return None


def is_mantra(node) -> bool:
    """Identify the base operator, including namespaced Mantra definitions."""
    node_type = node.type()
    components = getattr(node_type, "nameComponents", None)
    if callable(components):
        names = components()
        if isinstance(names, (list, tuple)) and len(names) == 4:
            return names[2] == "ifd"
    return node_type.name().split("::", 1)[0] == "ifd"


def read_render_resolution(hou, node) -> dict:
    """Read current resolution controls, including Mantra's camera inheritance.

    This describes the current parameter context, not a completed render or a
    different render take. Unknown controls never expose an inactive override
    as the effective resolution.
    """
    result = {"resolution": None, "resolution_source": "unresolved", "resolution_unresolved": []}
    if is_mantra(node):
        override = _resolution_scalar(node, ("override_camerares",))
        result["resolution_override_enabled"] = bool(override) if override is not None else None
        if override is None:
            result["resolution_unresolved"] = ["override_camerares"]
            return result
        if override:
            scale = _resolution_scalar(node, ("res_fraction",))
            result["resolution_scale"] = scale
            if scale == MANTRA_SPECIFIC_RESOLUTION:
                result["resolution"] = _resolution_pair(node, ("res_override",), ("res_overridex",), ("res_overridey",))
                result["resolution_source"] = "rop_override"
                if result["resolution"] is None:
                    result["resolution_unresolved"] = ["res_override"]
                return result
            try:
                fraction = float(scale)
                if not math.isfinite(fraction) or fraction <= 0:
                    raise ValueError("invalid resolution scale")
            except (TypeError, ValueError):
                result["resolution_unresolved"] = ["res_fraction"]
                return result
        else:
            fraction = 1.0
        camera_path = _resolution_scalar(node, ("camera", "render_camera"))
        camera = hou.node(camera_path) if camera_path else None
        if camera is None:
            result["resolution_unresolved"] = ["camera"]
            return result
        camera_resolution = _resolution_pair(camera, ("res",), ("resx",), ("resy",))
        if camera_resolution is None:
            result["resolution_unresolved"] = ["camera.res"]
            return result
        scaled = [value * fraction for value in camera_resolution]
        # Fractional pixels require renderer-specific rounding; do not guess.
        if any(value < 1 or int(value) != value for value in scaled):
            result["resolution_unresolved"] = ["fractional_camera_resolution"]
            return result
        result["resolution"] = [int(value) for value in scaled]
        result["resolution_source"] = "camera_scaled" if override else "camera"
        return result

    if node.parm("override_camerares") is not None:
        # Other camera-inheriting ROPs have their own scale/mode contracts.
        result["resolution_unresolved"] = ["renderer_resolution_controls"]
        return result
    override = _resolution_scalar(node, ("setres", "set_resolution"))
    result["resolution_override_enabled"] = bool(override) if override is not None else None
    if override is not None and not override:
        result["resolution_unresolved"] = ["resolution_override_disabled"]
        return result
    result["resolution"] = _resolution_pair(
        node, ("res_override", "res", "resolution"), RESOLUTION_X_PARMS, RESOLUTION_Y_PARMS
    )
    result["resolution_source"] = "rop" if result["resolution"] is not None else "unresolved"
    if result["resolution"] is None:
        result["resolution_unresolved"] = ["resolution_parameters"]
    return result


def set_render_resolution(node, resolution) -> bool:
    """Write a complete resolution and its renderer controls, never one axis."""
    mantra = is_mantra(node)
    if not mantra and node.parm("override_camerares") is not None:
        return False
    toggle = (
        node.parm("override_camerares")
        if mantra
        else next((node.parm(name) for name in ("setres", "set_resolution") if node.parm(name) is not None), None)
    )
    scale = node.parm("res_fraction") if mantra else None
    if mantra and (toggle is None or scale is None):
        return False
    tuple_names = ("res_override",) if mantra else ("res_override", "res", "resolution")
    target_tuple = next((node.parmTuple(name) for name in tuple_names if node.parmTuple(name) is not None), None)
    x_names = ("res_overridex",) if mantra else RESOLUTION_X_PARMS
    y_names = ("res_overridey",) if mantra else RESOLUTION_Y_PARMS
    x = next((node.parm(name) for name in x_names if node.parm(name) is not None), None)
    y = next((node.parm(name) for name in y_names if node.parm(name) is not None), None)
    if target_tuple is None and (x is None or y is None):
        return False
    if target_tuple is not None:
        if len(target_tuple.eval()) != 2:
            return False
        target_tuple.set(tuple(resolution))
    else:
        x.set(resolution[0])
        y.set(resolution[1])
    if scale is not None:
        scale.set(MANTRA_SPECIFIC_RESOLUTION)
    if toggle is not None:
        toggle.set(True)
    return True


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
