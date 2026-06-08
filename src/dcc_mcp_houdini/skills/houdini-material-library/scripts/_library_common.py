"""Shared helpers for Houdini material-library skills."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dcc_mcp_core.skill import skill_error

ENV_LIBRARY_DIR = "DCC_MCP_HOUDINI_MATERIAL_LIBRARY_DIR"

# Known texture file-node type names (checked in priority order).
TEXTURE_NODE_TYPES = [
    "arnold::image",
    "mtlximage",
    "redshift::TextureSampler",
    "principledtexture",
    "composite",
    "file",
]

# Parameter names that store a file path on image nodes.
IMAGE_FILE_PARMS = ("filename", "file", "texturefile", "tex0", "map")

# Parameter names that store a material assignment on OBJ/SOP nodes.
MATERIAL_ASSIGN_PARMS = ("shop_materialpath", "shop_materialpath1", "material")


def library_dir(base: Optional[str] = None) -> Path:
    """Return the material-library directory (created on demand).

    Priority:
    1. Explicit *base* argument.
    2. ``DCC_MCP_HOUDINI_MATERIAL_LIBRARY_DIR`` environment variable.
    3. ``~/.dcc-mcp/houdini/material_library/``.
    """
    if base:
        target = Path(base)
    else:
        override = os.environ.get(ENV_LIBRARY_DIR)
        target = Path(override) if override else Path.home() / ".dcc-mcp" / "houdini" / "material_library"
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def hou_import_error() -> dict:
    """Standard error when the HOM module is unavailable."""
    return skill_error("Houdini not available", "hou could not be imported")


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def coerce_value(value: Any, current: Any) -> Any:
    """Best-effort coerce *value* to the type of *current*."""
    if current is None:
        return value
    try:
        if isinstance(current, bool):
            return bool(value)
        if isinstance(current, int) and not isinstance(current, bool):
            return int(value)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, str):
            return str(value)
    except (TypeError, ValueError):
        return value
    return value


def set_node_parameter(node: Any, name: str, value: Any) -> Any:
    """Set a parameter on *node* and return the coerced value set."""
    if isinstance(value, (list, tuple)):
        parm_tuple = node.parmTuple(name)
        if parm_tuple is None:
            raise ValueError("No parameter tuple named {!r} on {}".format(name, node.path()))
        parm_tuple.set(tuple(value))
        return list(value)
    parm = node.parm(name)
    if parm is None:
        raise ValueError("No parameter named {!r} on {}".format(name, node.path()))
    try:
        current = parm.eval()
    except Exception:  # noqa: BLE001
        current = None
    coerced = coerce_value(value, current)
    parm.set(coerced)
    return coerced


def find_image_filepath(node: Any) -> Optional[str]:
    """Return the file path referenced by an image/texture node, or None."""
    for parm_name in IMAGE_FILE_PARMS:
        parm = node.parm(parm_name)
        if parm is None:
            continue
        try:
            value = parm.eval()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, str) and value.strip():
            return value
    return None


def is_image_node(node: Any) -> bool:
    """Return True if *node* looks like a file-texture node."""
    type_name = node.type().name() if hasattr(node.type(), "name") else ""
    for candidate in TEXTURE_NODE_TYPES:
        if candidate in type_name:
            return True
    # Fallback: check for a filename/file parameter with a non-empty path.
    return find_image_filepath(node) is not None


def iter_nodes_recursive(parent: Any) -> Any:
    """Yield every node under *parent* recursively."""
    yield parent
    for child in parent.children():
        yield from iter_nodes_recursive(child)


def find_material_assignment_parm(node: Any) -> Optional[Any]:
    """Return the first material assignment parm set on *node*, or None."""
    for pname in MATERIAL_ASSIGN_PARMS:
        parm = node.parm(pname)
        if parm is None:
            continue
        try:
            value = parm.eval()
        except Exception:  # noqa: BLE001
            continue
        if value and isinstance(value, str) and value.strip():
            return parm
    return None
