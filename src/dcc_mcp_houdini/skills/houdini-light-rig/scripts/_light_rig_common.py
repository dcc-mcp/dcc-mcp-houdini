"""Shared helpers for Houdini light-rig skills."""

from __future__ import annotations

from typing import Any, Optional, Sequence

# Friendly light type -> hlight 'light_type' menu index (hlight::2.0).
LIGHT_TYPES = {
    "point": 0,
    "line": 1,
    "grid": 2,
    "disk": 3,
    "sphere": 4,
    "tube": 5,
    "geometry": 6,
    "distant": 7,
    "sun": 7,
    "environment": 8,
}

# Shape types that support area light parameters (areasize, etc.)
AREA_SHAPES = {"grid", "disk", "sphere", "tube"}


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


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


def eval_parm(node: Any, name: str) -> Optional[Any]:
    """Eval a scalar parm or parm tuple if present, else None."""
    parm_tuple = node.parmTuple(name)
    if parm_tuple is not None:
        try:
            values = list(parm_tuple.eval())
            return values[0] if len(values) == 1 else values
        except Exception:  # noqa: BLE001
            return None
    parm = node.parm(name)
    if parm is not None:
        try:
            return parm.eval()
        except Exception:  # noqa: BLE001
            return None
    return None


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def apply_transform(
    node: Any,
    translate: Optional[Sequence[float]],
    rotate: Optional[Sequence[float]],
    scale: Optional[Sequence[float]] = None,
) -> dict:
    """Set t/r/s parm tuples defensively; return what was applied."""
    applied: dict = {}
    if translate is not None and set_parm_if_exists(node, "t", translate):
        applied["t"] = list(translate)
    if rotate is not None and set_parm_if_exists(node, "r", rotate):
        applied["r"] = list(rotate)
    if scale is not None and set_parm_if_exists(node, "s", scale):
        applied["s"] = list(scale)
    return applied


def _menu_index(value: Any) -> Optional[int]:
    """Normalize Houdini menu values that may be wrapped by a parm tuple."""
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_light_parms(light: Any) -> dict:
    """Read common hlight parameters and return a JSON-safe dict."""
    node_type = light.type().name().lower()
    type_index = _menu_index(eval_parm(light, "light_type"))
    type_name = "environment" if "envlight" in node_type else None
    if type_name is None and type_index is not None:
        for name, idx in LIGHT_TYPES.items():
            if idx == type_index and name != "sun":
                type_name = name
                break

    parms = {
        "path": light.path(),
        "name": light.name(),
        "type": type_name,
        "type_index": type_index,
        "intensity": eval_parm(light, "light_intensity"),
        "color": eval_parm(light, "light_color"),
        "exposure": eval_parm(light, "light_exposure"),
        "translate": eval_parm(light, "t"),
        "rotate": eval_parm(light, "r"),
        "enabled": eval_parm(light, "light_enable"),
    }

    if type_name in AREA_SHAPES:
        parms["area_size"] = eval_parm(light, "areasize")

    if type_name == "environment":
        parms["env_map"] = eval_parm(light, "env_map") or eval_parm(light, "envmap")

    parms["contrib_diffuse"] = eval_parm(light, "light_contribdiff")
    if parms["contrib_diffuse"] is None:
        parms["contrib_diffuse"] = eval_parm(light, "light_contribdiffuse")
    parms["contrib_specular"] = eval_parm(light, "light_contribspec")
    if parms["contrib_specular"] is None:
        parms["contrib_specular"] = eval_parm(light, "light_contribspecular")

    return parms


def is_light_node(node: Any) -> bool:
    """Check if a node is a native Houdini light."""
    type_name = node.type().name() if hasattr(node.type(), "name") else ""
    return any(name in type_name.lower() for name in ("hlight", "envlight"))


def is_rig_null(node: Any) -> bool:
    """Check if a node is a null node that acts as a light rig parent."""
    type_name = node.type().name() if hasattr(node.type(), "name") else ""
    if "null" not in type_name.lower():
        return False
    # A rig null has at least one hlight child
    for child in node.children():
        if is_light_node(child):
            return True
    return False


def get_rig_members(rig_node: Any) -> list:
    """Return all hlight children under a rig null node."""
    lights = []
    for child in rig_node.children():
        if is_light_node(child):
            lights.append(child)
    return lights
