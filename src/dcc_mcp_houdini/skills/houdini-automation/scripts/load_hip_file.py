"""Load a Houdini hip file."""

from __future__ import annotations

from _automation_common import existing_file, hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def load_hip_file(file_path: str, suppress_save_prompt: bool = True) -> dict:
    """Load a hip file into the current Houdini session."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        path = existing_file(file_path, suffixes={".hip", ".hiplc", ".hipnc"})
        hou.hipFile.load(str(path), suppress_save_prompt=suppress_save_prompt)
        return skill_success("Loaded Houdini hip file", hip_file=str(path))
    except Exception as exc:
        return skill_exception(exc, message="Failed to load Houdini hip file")


@skill_entry
def main(**kwargs) -> dict:
    return load_hip_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
