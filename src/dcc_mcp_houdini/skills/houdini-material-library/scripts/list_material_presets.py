"""List all material preset JSON files in a library directory (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import _library_common  # noqa: E402


def list_material_presets(library_dir: Optional[str] = None) -> dict:
    """List all material preset JSON files in a library directory.

    Args:
        library_dir: Directory to search for .json preset files.
            Defaults to the configured or default library directory.

    Returns:
        ToolResult dict with a list of preset info dicts.
    """
    try:
        base = _library_common.library_dir(library_dir)
        if not base.is_dir():
            return skill_error(
                "Library directory not found: {}".format(base),
                "Create the directory or run save_material_preset first.",
            )

        presets = []
        for path in sorted(base.glob("*.json")):
            entry = {
                "name": path.stem,
                "file_path": str(path),
                "size_bytes": path.stat().st_size,
            }
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
                entry["material_type"] = data.get("material_type", "unknown")
                entry["source_material"] = data.get("material_path", "unknown")
                entry["parameter_count"] = len(data.get("parameters", {}))
            except Exception:  # noqa: BLE001
                entry["error"] = "unreadable preset"
            presets.append(entry)

        return skill_success(
            "Listed material presets",
            library_dir=str(base),
            count=len(presets),
            presets=presets,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list material presets")


@skill_entry
def main(**kwargs) -> dict:
    return list_material_presets(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
