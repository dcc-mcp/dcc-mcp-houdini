"""Shared helpers for Houdini export-preset skills."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from dcc_mcp_core.skill import skill_error

ENV_PRESET_DIR = "DCC_MCP_HOUDINI_EXPORT_PRESET_DIR"

# ROP node type → format name mapping.
ROP_TYPE_FORMATS: Dict[str, str] = {
    "alembic": "alembic",
    "rop_alembic": "alembic",
    "filmboxfbx": "fbx",
    "rop_fbx": "fbx",
    "usdrender": "usd",
    "usd_rop": "usd",
    "geometry": "geometry",
    "ifd": "ifd",
    "opengl": "opengl",
    "Redshift_ROP": "redshift",
    "karma": "karma",
}

# Known parameter names for the source/sop path on ROP nodes.
ROP_SOURCE_PARMS = ("soppath", "loppath", "sop_path", "lop_path", "sopoutput", "rootnode")


def library_dir(base: Optional[str] = None) -> Path:
    """Return the export-preset library directory (created on demand).

    Priority:
    1. Explicit *base* argument.
    2. ``DCC_MCP_HOUDINI_EXPORT_PRESET_DIR`` environment variable.
    3. ``~/.dcc-mcp/houdini/export_presets/``.
    """
    if base:
        target = Path(base)
    else:
        override = os.environ.get(ENV_PRESET_DIR)
        target = Path(override) if override else Path.home() / ".dcc-mcp" / "houdini" / "export_presets"
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


def detect_format_from_type(type_name: str) -> str:
    """Map a ROP node type name to a format string."""
    if not type_name:
        return "geometry"
    for key, fmt in ROP_TYPE_FORMATS.items():
        if key.lower() in type_name.lower():
            return fmt
    return "geometry"


def find_rop_in_out(hou: Any, source_node_path: Optional[str] = None) -> Optional[Any]:
    """Find the first ROP node in /out, optionally matching a source path."""
    out_node = hou.node("/out")
    if out_node is None:
        return None

    for child in out_node.children():
        # Skip non-ROP nodes (e.g. nulls, subnets).
        type_name = child.type().name() if hasattr(child.type(), "name") else ""
        if not type_name:
            continue

        if source_node_path:
            for parm_name in ROP_SOURCE_PARMS:
                parm = child.parm(parm_name)
                if parm is not None:
                    try:
                        value = parm.eval()
                    except Exception:  # noqa: BLE001
                        continue
                    if value and str(value) == source_node_path:
                        return child
        else:
            # Return the first real ROP node (skip non-RON types).
            try:
                if hasattr(child.type(), "category"):
                    if child.type().category().name() == "Driver":
                        return child
            except Exception:  # noqa: BLE001
                pass

    return None


def find_source_path(rop_node: Any) -> Optional[str]:
    """Return the source SOP/LOP path from a ROP node, or None."""
    for parm_name in ROP_SOURCE_PARMS:
        parm = rop_node.parm(parm_name)
        if parm is not None:
            try:
                value = parm.eval()
            except Exception:  # noqa: BLE001
                continue
            if value and isinstance(value, str) and value.strip():
                return value
    return None
