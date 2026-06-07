"""List all export preset JSON files in a library directory (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import _export_preset_common  # noqa: E402


def list_export_presets(library_dir: Optional[str] = None) -> dict:
    """List all export preset JSON files in a library directory.

    Args:
        library_dir: Directory to search for .json preset files.
            Defaults to the configured default library directory.

    Returns:
        ToolResult dict with a list of preset info dicts.
    """
    try:
        base = _export_preset_common.library_dir(library_dir)
        if not base.is_dir():
            return skill_success(
                "No export presets directory found",
                presets=[],
                count=0,
                library_dir=str(base),
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
                entry["format"] = data.get("format", "unknown")
                entry["rop_type"] = data.get("rop_type", "unknown")
                entry["source_node_path"] = data.get("source_node_path")
                entry["frame_range"] = data.get("frame_range")
                entry["parameter_count"] = len(data.get("rop_parameters", {}))
            except Exception:  # noqa: BLE001
                entry["error"] = "unreadable preset"
            presets.append(entry)

        return skill_success(
            "Listed export presets",
            library_dir=str(base),
            count=len(presets),
            presets=presets,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list export presets")


@skill_entry
def main(**kwargs) -> dict:
    return list_export_presets(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
