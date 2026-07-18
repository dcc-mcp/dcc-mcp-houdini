"""Delete a material preset JSON file from the library."""

from __future__ import annotations

from typing import Optional

import _library_common  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def delete_material_preset(preset_name: str, library_dir: Optional[str] = None) -> dict:
    """Delete a material preset JSON file from the library.

    Args:
        preset_name: Name of the preset file to delete (stem without .json).
        library_dir: Directory containing .json preset files.

    Returns:
        ToolResult dict confirming deletion.
    """
    try:
        base = _library_common.library_dir(library_dir)
        target = base / "{}.json".format(preset_name)

        if not target.is_file():
            # Try fuzzy match (allow passing the sanitized stem directly).
            candidates = list(base.glob("*.json"))
            for candidate in candidates:
                if candidate.stem == preset_name:
                    target = candidate
                    break
            else:
                return skill_error(
                    "Preset not found: {!r}".format(preset_name),
                    "Use list_material_presets to find available preset names.",
                    library_dir=str(base),
                )

        target.unlink()
        return skill_success(
            "Deleted material preset",
            preset_name=preset_name,
            preset_path=str(target),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to delete material preset")


@skill_entry
def main(**kwargs) -> dict:
    return delete_material_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
