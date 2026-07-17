"""Synchronize an HDA instance with a loaded definition and version handler."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_common import validate_hda_path  # noqa: E402


def sync_hda_instance(
    node_path: str,
    from_version: str,
    hda_file: Optional[str] = None,
    match_current: bool = True,
    sync_delayed: bool = True,
) -> dict:
    """Reload an optional library and run the HDA version synchronization hook."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not isinstance(from_version, str) or not from_version.strip():
            raise ValueError("from_version must be a non-empty string")
        from_version = from_version.strip()
        if hda_file:
            path = validate_hda_path(hda_file, must_exist=True)
            normalized = os.path.normcase(os.path.abspath(str(path)))
            loaded = {os.path.normcase(os.path.abspath(item)) for item in hou.hda.loadedFiles()}
            if normalized in loaded:
                hou.hda.reloadFile(str(path))
            else:
                hou.hda.installFile(str(path))

        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node not found: {}".format(node_path))
        definition = node.type().definition()
        if definition is None:
            raise ValueError("Node is not a Houdini Digital Asset: {}".format(node_path))

        delayed = bool(node.isDelayedDefinition())
        if sync_delayed and delayed:
            node.syncDelayedDefinition()
        if match_current and not node.matchesCurrentDefinition():
            node.matchCurrentDefinition()
        node.syncNodeVersionIfNeeded(from_version)

        return skill_success(
            "Synchronized HDA instance",
            node_path=node.path(),
            node_type_name=definition.nodeTypeName(),
            library_path=definition.libraryFilePath(),
            from_version=from_version,
            version=definition.version(),
            delayed_definition_synced=bool(sync_delayed and delayed),
            matched_current_definition=node.matchesCurrentDefinition(),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to synchronize HDA instance")


@skill_entry
def main(**kwargs) -> dict:
    return sync_hda_instance(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
