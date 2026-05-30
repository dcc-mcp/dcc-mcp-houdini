"""Scan installed/loaded HDA libraries and count their definitions."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


def scan_hda_libraries() -> dict:
    """Return loaded HDA files with their definition node-type names."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        loaded = list(hou.hda.loadedFiles()) if hasattr(hou.hda, "loadedFiles") else []
        libraries = []
        for path in loaded:
            entry = {"library_path": path}
            try:
                defs = hou.hda.definitionsInFile(path)
                entry["definition_count"] = len(defs)
                entry["node_types"] = [d.nodeTypeName() for d in defs]
            except Exception as exc:  # noqa: BLE001
                entry["error"] = str(exc)
            libraries.append(entry)
        return skill_success(
            "Scanned HDA libraries",
            count=len(libraries),
            libraries=libraries,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to scan HDA libraries")


@skill_entry
def main(**kwargs) -> dict:
    return scan_hda_libraries(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
