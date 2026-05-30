"""Reset object material assignments to a default (or clear them)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _lookdev_common import MATERIAL_ASSIGN_PARMS, get_node  # noqa: E402


def reset_material(object_paths: List[str], default_material: str = "") -> dict:
    """Set each object's material assignment to *default_material* (default empty)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if not object_paths:
        return skill_error("No objects", "Provide at least one object path")

    try:
        affected = []
        skipped = []
        for path in object_paths:
            node = get_node(hou, path)
            applied = False
            for parm_name in MATERIAL_ASSIGN_PARMS:
                parm = node.parm(parm_name)
                if parm is not None:
                    parm.set(default_material)
                    applied = True
                    break
            (affected if applied else skipped).append(node.path())
        return skill_success(
            "Reset material assignments",
            default_material=default_material,
            affected=affected,
            skipped=skipped,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to reset material assignments")


@skill_entry
def main(**kwargs) -> dict:
    return reset_material(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
