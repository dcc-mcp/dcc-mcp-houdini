"""Save the current Houdini hip file."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from _automation_common import hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def save_hip_file(file_path: Optional[str] = None) -> dict:
    """Save through a sibling temporary file, then atomically replace the target."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    temporary = None
    temporary_saved = False
    previous_name = None
    try:
        previous_name = hou.hipFile.name()
        target = Path(file_path or hou.hipFile.path()).expanduser().resolve()
        if target.suffix.lower() not in {".hip", ".hiplc", ".hipnc"}:
            raise ValueError("Houdini scene path must end in .hip, .hiplc, or .hipnc")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(".{}.{}.tmp{}".format(target.stem, uuid.uuid4().hex, target.suffix))
        hou.hipFile.save(file_name=str(temporary), save_to_recent_files=False)
        temporary_saved = True
        hou.hipFile.setName(str(target))
        os.replace(str(temporary), str(target))
        return skill_success("Saved Houdini hip file", hip_file=str(target), atomic_replace=True)
    except Exception as exc:
        recovery_file = str(temporary) if temporary_saved and temporary is not None and temporary.exists() else None
        try:
            hou.hipFile.setName(recovery_file or previous_name)
        except Exception:
            pass
        if not temporary_saved and temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
        return skill_exception(
            exc,
            message="Failed to save Houdini hip file",
            recovery_file=recovery_file,
        )


@skill_entry
def main(**kwargs) -> dict:
    return save_hip_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
