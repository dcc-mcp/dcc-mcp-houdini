"""Uninstall a loaded Houdini Digital Asset library from the current session."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from _hda_common import definition_summary, hou_import_error, validate_hda_library_path
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def _normalize(path: str) -> str:
    """Best-effort canonical form for comparing library paths across platforms."""
    expanded = os.path.expanduser(path)
    try:
        resolved = str(Path(expanded).resolve())
    except OSError:
        resolved = os.path.normpath(expanded)
    return os.path.normcase(resolved)


def _match_loaded_library(hou: Any, requested: str) -> Optional[str]:
    """Return the loadedFiles() entry matching *requested*, or None if not loaded."""
    target = _normalize(requested)
    for loaded in hou.hda.loadedFiles():
        if _normalize(str(loaded)) == target:
            return str(loaded)
    return None


def _definition_identities(hou: Any, library: str) -> list:
    """Snapshot (category, node type name) for every definition in *library*.

    Captured before uninstall so the post-uninstall registration check still has
    the category objects needed to look each node type up again.
    """
    identities = []
    try:
        definitions = hou.hda.definitionsInFile(library)
    except Exception:  # noqa: BLE001 - a missing/corrupt file still allows uninstall
        return identities
    for definition in definitions:
        node_type = getattr(definition, "nodeType", None)
        category = node_type().category() if callable(node_type) else None
        identities.append((category, definition.nodeTypeName()))
    return identities


def _unregistered(hou: Any, identities: list) -> list:
    """Return node type names that are no longer registered after uninstall."""
    unregistered = []
    for category, type_name in identities:
        try:
            if hou.nodeType(category, type_name) is None:
                unregistered.append(type_name)
        except Exception:  # noqa: BLE001 - treat lookup failure as unregistered
            unregistered.append(type_name)
    return unregistered


def uninstall_hda_file(file_path: str) -> dict:
    """Uninstall a loaded HDA/OTL library from the current Houdini session.

    This is a session-level operation only: the library file on disk is never
    modified or deleted, and reinstalling the same file restores the definitions
    (and re-links existing instances). Removing a library whose definitions are
    still in use marks those instances incomplete for the current session until
    the library is reinstalled.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        path = validate_hda_library_path(file_path)
        loaded = _match_loaded_library(hou, str(path))
        if loaded is None:
            # Idempotent no-op: uninstalling a library that is not loaded leaves
            # the session unchanged and is reported as success.
            return skill_success(
                "HDA library was not loaded; nothing to uninstall",
                file_path=str(path),
                was_loaded=False,
                still_loaded=False,
                removed_definitions=[],
                removed_definition_count=0,
                session_only=True,
            )

        definitions = [definition_summary(defn, loaded) for defn in hou.hda.definitionsInFile(loaded)]
        identities = _definition_identities(hou, loaded)
        hou.hda.uninstallFile(loaded)
        still_loaded = _match_loaded_library(hou, loaded) is not None
        unregistered = _unregistered(hou, identities)

        return skill_success(
            "Uninstalled Houdini Digital Asset library",
            file_path=loaded,
            was_loaded=True,
            still_loaded=still_loaded,
            removed_definitions=definitions,
            removed_definition_count=len(definitions),
            unregistered_node_types=unregistered,
            session_only=True,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to uninstall Houdini Digital Asset file")


@skill_entry
def main(**kwargs) -> dict:
    return uninstall_hda_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
