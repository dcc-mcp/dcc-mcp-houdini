"""Shared helpers for Houdini mesh-operation skills."""

from __future__ import annotations

from typing import Any, Optional


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def make_downstream_sop(input_node: Any, optype: str, name: Optional[str] = None) -> Any:
    """Create and wire *optype*, transferring ownership only on success."""
    parent = input_node.parent()
    if parent is None:
        raise ValueError("Input node has no parent network: {}".format(input_node.path()))
    new_node = None
    try:
        new_node = parent.createNode(optype, node_name=name)
        new_node.setInput(0, input_node)
        if hasattr(new_node, "moveToGoodPosition"):
            try:
                new_node.moveToGoodPosition()
            except Exception:  # noqa: BLE001
                pass
        if hasattr(new_node, "setDisplayFlag"):
            new_node.setDisplayFlag(True)
        return new_node
    except BaseException:
        if new_node is not None:
            try:
                new_node.destroy()
            except BaseException:
                pass
        raise


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


def _template_label(parm: Any) -> str:
    try:
        return str(parm.parmTemplate().label())
    except Exception:  # noqa: BLE001
        return ""


def find_scalar_parm(node: Any, candidates: tuple, labels: tuple = ()) -> Any:
    """Find a scalar parm by stable internal name, then by exact UI label."""
    for name in candidates:
        parm = node.parm(name)
        if parm is not None:
            return parm
    accepted = {_normalized_label(label) for label in labels}
    if accepted and hasattr(node, "parms"):
        matches = [parm for parm in node.parms() if _normalized_label(_template_label(parm)) in accepted]
        if len(matches) == 1:
            return matches[0]
    raise RuntimeError("Required parameter is unavailable: {}".format("/".join(candidates)))


def find_tuple_parm(node: Any, candidates: tuple, labels: tuple = ()) -> Any:
    """Find a tuple parm by stable internal name, then by exact UI label."""
    for name in candidates:
        parm_tuple = node.parmTuple(name)
        if parm_tuple is not None:
            return parm_tuple
    accepted = {_normalized_label(label) for label in labels}
    if accepted and hasattr(node, "parmTuples"):
        matches = [
            parm_tuple for parm_tuple in node.parmTuples() if _normalized_label(_template_label(parm_tuple)) in accepted
        ]
        if len(matches) == 1:
            return matches[0]
    raise RuntimeError("Required tuple parameter is unavailable: {}".format("/".join(candidates)))


def set_scalar_parm_verified(
    node: Any,
    candidates: tuple,
    value: Any,
    labels: tuple = (),
) -> Any:
    """Set a required scalar parm and return its verified value."""
    parm = find_scalar_parm(node, candidates, labels)
    parm.set(value)
    actual = parm.eval()
    if isinstance(value, bool):
        matches = bool(actual) is value
    elif isinstance(value, (int, float)):
        matches = abs(float(actual) - float(value)) <= 1e-8
    else:
        matches = str(actual) == str(value)
    if not matches:
        raise RuntimeError("Parameter readback did not match: {}".format(candidates[0]))
    return actual


def set_tuple_parm_verified(
    node: Any,
    candidates: tuple,
    values: tuple,
    labels: tuple = (),
) -> tuple:
    """Set a required tuple parm and return its verified numeric values."""
    parm_tuple = find_tuple_parm(node, candidates, labels)
    requested = tuple(float(value) for value in values)
    parm_tuple.set(requested)
    actual = tuple(float(value) for value in parm_tuple.eval())
    if len(actual) != len(requested) or any(
        abs(actual[index] - requested[index]) > 1e-8 for index in range(len(requested))
    ):
        raise RuntimeError("Tuple parameter readback did not match: {}".format(candidates[0]))
    return actual


def _normalized_label(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def set_menu_parm_candidates(
    node: Any,
    candidates: tuple,
    accepted_labels: tuple,
    parameter_labels: tuple = (),
) -> str:
    """Resolve a menu parameter and token by labels, then verify readback."""
    parm = find_scalar_parm(node, candidates, parameter_labels)
    if not hasattr(parm, "menuItems") or not hasattr(parm, "menuLabels"):
        raise RuntimeError("Parameter is not a menu: {}".format(candidates[0]))
    items = tuple(parm.menuItems())
    labels = tuple(parm.menuLabels())
    if len(items) != len(labels) or not items:
        raise RuntimeError("Menu parameter has no stable items: {}".format(candidates[0]))
    accepted = {_normalized_label(value) for value in accepted_labels}
    matches = [item for item, label in zip(items, labels) if _normalized_label(label) in accepted]
    if len(matches) != 1:
        raise RuntimeError("Menu parameter {} did not expose exactly one accepted label".format(candidates[0]))
    token = str(matches[0])
    parm.set(token)
    actual = None
    if hasattr(parm, "evalAsString"):
        try:
            actual = str(parm.evalAsString())
        except Exception:  # noqa: BLE001
            pass
    if actual != token:
        raw = parm.eval()
        if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw < len(items):
            actual = str(items[raw])
        else:
            actual = str(raw)
    if actual != token:
        raise RuntimeError("Menu parameter {} readback did not match".format(candidates[0]))
    return token


def set_menu_parm(node: Any, name: str, accepted_labels: tuple) -> str:
    """Resolve one named menu parameter token by label and verify readback."""
    return set_menu_parm_candidates(node, (name,), accepted_labels)


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def geometry_readback(node: Any) -> dict:
    """Return bounded cooked-geometry evidence without enumerating components."""
    geometry = node.geometry()
    if geometry is None:
        raise RuntimeError("SOP produced no geometry")
    bounds = geometry.boundingBox()
    return {
        "point_count": int(geometry.pointCount()),
        "primitive_count": int(geometry.primCount()),
        "vertex_count": int(geometry.vertexCount()),
        "bounds_min": [float(value) for value in bounds.minvec()],
        "bounds_max": [float(value) for value in bounds.maxvec()],
        "bounds_size": [float(value) for value in bounds.sizevec()],
    }


def geometry_changed(before: dict, after: dict) -> bool:
    """Return whether bounded topology or bounds evidence changed."""
    keys = ("point_count", "primitive_count", "vertex_count", "bounds_min", "bounds_max")
    return any(before[key] != after[key] for key in keys)


def cook_readback(node: Any, before: Optional[dict] = None, require_change: bool = True) -> dict:
    """Cook a SOP and fail unless its bounded post-condition is observable."""
    node.cook(force=True)
    errors = [str(value) for value in (node.errors() or [])]
    if errors:
        raise RuntimeError("SOP cook failed: {}".format("; ".join(errors)))
    after = geometry_readback(node)
    if after["primitive_count"] <= 0:
        raise RuntimeError("SOP geometry readback is empty")
    if before is not None and require_change and not geometry_changed(before, after):
        raise RuntimeError("SOP geometry readback reported no observable effect")
    after["verified"] = True
    if before is not None:
        after["before"] = before
    warnings = [str(value) for value in (node.warnings() or [])]
    if warnings:
        after["warnings"] = warnings
    return after
