"""Delete a saved material preset (adapter-owned JSON store)."""

from __future__ import annotations

from _lookdev_common import preset_dir  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def delete_preset(preset_name: str) -> dict:
    """Delete the preset named *preset_name* if it exists."""
    try:
        target = preset_dir() / "{}.json".format(preset_name)
        if not target.is_file():
            return skill_error(
                "Preset not found",
                "No preset named {!r}".format(preset_name),
                preset_dir=str(preset_dir()),
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
    return delete_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
