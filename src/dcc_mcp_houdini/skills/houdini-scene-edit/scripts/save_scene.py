"""Save the current Houdini hip file."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def save_scene(file_path: Optional[str] = None) -> dict:
    """Save the scene.

    With no ``file_path`` the current hip path is reused (must already be
    saved at least once); otherwise the scene is saved to ``file_path``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if file_path:
            hou.hipFile.save(file_name=file_path)
        else:
            if not hou.hipFile.hasFile():
                return skill_error(
                    "Scene has never been saved",
                    "No hip path is set; pass file_path to choose a destination",
                    possible_solutions=["Call save_scene with an explicit file_path"],
                )
            hou.hipFile.save()
        return skill_success("Saved hip file", file_path=hou.hipFile.path())
    except Exception as exc:
        return skill_exception(exc, message="Failed to save hip file")


@skill_entry
def main(**kwargs) -> dict:
    return save_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
