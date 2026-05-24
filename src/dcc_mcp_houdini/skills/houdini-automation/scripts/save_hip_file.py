"""Save the current Houdini hip file."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _automation_common import hou_import_error


def save_hip_file(file_path: Optional[str] = None) -> dict:
    """Save the current Houdini hip file."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        resolved = None
        if file_path:
            resolved_path = Path(file_path).expanduser()
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            resolved = str(resolved_path)
            hou.hipFile.save(file_name=resolved)
        else:
            hou.hipFile.save()
            resolved = hou.hipFile.name() if hou.hipFile.hasFile() else None
        return skill_success("Saved Houdini hip file", hip_file=resolved)
    except Exception as exc:
        return skill_exception(exc, message="Failed to save Houdini hip file")


@skill_entry
def main(**kwargs) -> dict:
    return save_hip_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
