"""Shared helpers for Houdini automation skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_error

from dcc_mcp_houdini.api import set_parm_value as set_parm_value


def hou_import_error() -> dict:
    """Standard error when the HOM module is unavailable."""
    return skill_error("Houdini not available", "hou could not be imported")


def existing_file(path: str, *, suffixes: set = None) -> Path:
    """Resolve an existing file and optionally validate its suffix."""
    resolved = Path(path).expanduser()
    if not resolved.is_file():
        raise FileNotFoundError("File not found: {}".format(resolved))
    if suffixes and resolved.suffix.lower() not in suffixes:
        raise ValueError("Unsupported file extension: {}".format(resolved.suffix))
    return resolved


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }
