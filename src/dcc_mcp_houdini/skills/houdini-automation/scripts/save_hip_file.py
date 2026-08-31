"""Save the current Houdini hip file."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from _automation_common import hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._hip_file_state import get_hip_dirty_state


def save_hip_file(file_path: Optional[str] = None) -> dict:
    """Save through a sibling temporary file, then atomically replace the target."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    temporary = None
    temporary_saved = False
    target_replaced = False
    recovery_staged = False
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
        target_replaced = True

        ui_available = bool(hou.isUIAvailable())
        dirty_state = get_hip_dirty_state(hou)
        atomic_replace = True
        if dirty_state is True:
            # Save As is the documented HOM operation that clears GUI dirty
            # state. Preserve the atomic replacement separately in case this
            # final state-confirming save partially overwrites the target.
            shutil.copy2(str(target), str(temporary))
            recovery_staged = True
            hou.hipFile.save(file_name=str(target), save_to_recent_files=False)
            atomic_replace = False
            dirty_state = get_hip_dirty_state(hou)
        if ui_available and dirty_state is not False:
            raise RuntimeError("Houdini still reports unsaved changes after saving the HIP file")
        if recovery_staged:
            temporary.unlink()
            recovery_staged = False
        return skill_success(
            "Saved Houdini hip file",
            hip_file=str(target),
            atomic_replace=atomic_replace,
            unsaved_changes=dirty_state,
        )
    except Exception as exc:
        if recovery_staged and temporary is not None and temporary.exists():
            recovery_file = str(temporary)
        elif not target_replaced and temporary_saved and temporary is not None and temporary.exists():
            recovery_file = str(temporary)
        elif target_replaced and target.exists():
            recovery_file = str(target)
        else:
            recovery_file = None
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
