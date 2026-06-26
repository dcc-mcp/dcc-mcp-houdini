"""Delete an export preset JSON file from the library."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import _export_preset_common  # noqa: E402


def delete_export_preset(preset_name: str, library_dir: Optional[str] = None) -> dict:
    """Delete an export preset JSON file from the library.

    Args:
        preset_name: Name of the preset file to delete (stem without .json).
        library_dir: Directory containing .json preset files.

    Returns:
        ToolResult dict confirming deletion.
    """
    try:
        base = _export_preset_common.library_dir(library_dir)
        target = base / "{}.json".format(preset_name)

        if not target.is_file():
            candidates = list(base.glob("*.json"))
            for candidate in candidates:
                if candidate.stem == preset_name:
                    target = candidate
                    break
            else:
                return skill_error(
                    "Export preset not found: {!r}".format(preset_name),
                    "Use list_export_presets to find available preset names.",
                    library_dir=str(base),
                )

        target.unlink()
        return skill_success(
            "Deleted export preset",
            preset_name=preset_name,
            preset_path=str(target),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to delete export preset")


@skill_entry
def main(**kwargs) -> dict:
    return delete_export_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
