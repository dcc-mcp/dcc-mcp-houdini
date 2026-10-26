"""Shared helpers for Houdini Digital Asset skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from dcc_mcp_core.skill import skill_error

from dcc_mcp_houdini.api import set_parm_value as set_parm_value

_HDA_SUFFIXES = {".hda", ".hdalc", ".hdanc", ".otl", ".otllc", ".otlnc"}


def hou_import_error() -> dict:
    """Standard error when the HOM module is unavailable."""
    return skill_error("Houdini not available", "hou could not be imported")


def validate_hda_path(file_path: str, *, must_exist: bool = True) -> Path:
    """Validate a packed file or expanded Houdini asset library path."""
    path = Path(file_path).expanduser()
    if path.suffix.lower() not in _HDA_SUFFIXES:
        raise ValueError("Unsupported HDA file extension: {}".format(path.suffix))
    if must_exist:
        is_packed_library = path.is_file()
        is_expanded_library = path.is_dir() and (path / "Sections.list").is_file()
        if not (is_packed_library or is_expanded_library):
            raise FileNotFoundError("HDA library not found: {}".format(path))
    if not must_exist:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def validate_hda_library_path(file_path: str) -> Path:
    """Validate an HDA library path by extension only, without touching the filesystem.

    Used by session-level operations such as uninstalling a loaded library: the
    library may still be registered in the session even after its file has been
    removed from disk, and validating must never create parent directories as a
    side effect (unlike :func:`validate_hda_path` with ``must_exist=False``).
    """
    path = Path(file_path).expanduser()
    if path.suffix.lower() not in _HDA_SUFFIXES:
        raise ValueError("Unsupported HDA file extension: {}".format(path.suffix))
    return path


def definition_summary(definition: Any, source_file: str = "") -> dict:
    """Return a JSON-safe HDA definition summary."""
    node_type = definition.nodeType()
    category = node_type.category() if hasattr(node_type, "category") else None
    return {
        "node_type_name": definition.nodeTypeName(),
        "category": category.name() if category is not None and hasattr(category, "name") else None,
        "library_file_path": source_file or getattr(definition, "libraryFilePath", lambda: "")(),
        "description": getattr(definition, "description", lambda: "")(),
        "version": getattr(definition, "version", lambda: "")(),
    }


def definitions_in_file(hou: Any, file_path: str) -> list:
    """Return HDA definitions in a file as JSON-safe dicts."""
    path = validate_hda_path(file_path, must_exist=True)
    return [definition_summary(defn, str(path)) for defn in hou.hda.definitionsInFile(str(path))]


def press_buttons(node: Any, names: Iterable[str]) -> list:
    """Press button parameters and return names that were pressed."""
    pressed = []
    for name in names:
        parm = node.parm(name)
        if parm is None:
            raise ValueError("Button parameter {!r} not found on {}".format(name, node.path()))
        parm.pressButton()
        pressed.append(name)
    return pressed


def node_summary(node: Any) -> dict:
    """Return a small node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }
