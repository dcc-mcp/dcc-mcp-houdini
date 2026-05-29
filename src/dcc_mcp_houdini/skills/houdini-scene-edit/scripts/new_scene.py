"""Start a new (empty) Houdini scene with a dirty-scene safeguard."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def new_scene(force: bool = False) -> dict:
    """Clear the current hip file.

    Refuses to discard unsaved changes unless ``force`` is ``True``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not force and hou.hipFile.hasUnsavedChanges():
            return skill_error(
                "Scene has unsaved changes",
                "Refusing to clear the scene; save first or call with force=true",
                possible_solutions=[
                    "Call houdini_scene_edit__save_scene first",
                    "Re-run new_scene with force=true to discard changes",
                ],
            )
        hou.hipFile.clear(suppress_save_prompt=True)
        return skill_success("Started a new scene", forced=bool(force))
    except Exception as exc:
        return skill_exception(exc, message="Failed to start a new scene")


@skill_entry
def main(**kwargs) -> dict:
    return new_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
