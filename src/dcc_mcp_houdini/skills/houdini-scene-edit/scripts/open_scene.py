"""Open an existing Houdini hip file with a dirty-scene safeguard."""

from __future__ import annotations

import os

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini._hip_file_state import get_hip_dirty_state


def open_scene(file_path: str, force: bool = False) -> dict:
    """Load *file_path* into the current session.

    Requires a known-clean scene unless ``force`` is ``True``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not os.path.isfile(file_path):
            return skill_error("Hip file not found", "No file at: {}".format(file_path))
        if not force:
            dirty = get_hip_dirty_state(hou)
            if dirty is True:
                return skill_error(
                    "Scene has unsaved changes",
                    "Refusing to load over unsaved changes; save first or call with force=true",
                    possible_solutions=[
                        "Call houdini_scene_edit__save_scene first",
                        "Re-run open_scene with force=true to discard changes",
                    ],
                )
            if dirty is None:
                return skill_error(
                    "Scene dirty state unavailable",
                    "Cannot safely load over the current scene when its dirty state is unknown; call with force=true to discard it",
                    possible_solutions=["Re-run open_scene with force=true to discard the current scene"],
                )
        hou.hipFile.load(file_path, suppress_save_prompt=True, ignore_load_warnings=False)
        return skill_success(
            "Opened hip file",
            file_path=hou.hipFile.path(),
            forced=bool(force),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to open hip file")


@skill_entry
def main(**kwargs) -> dict:
    return open_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
