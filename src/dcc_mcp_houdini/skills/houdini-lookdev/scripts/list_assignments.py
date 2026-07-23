"""List object → material assignments under a network (read-only)."""

from __future__ import annotations

from _lookdev_common import MATERIAL_ASSIGN_PARMS, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini.api import safe_parm_eval


def list_assignments(parent_path: str = "/obj") -> dict:
    """Return material assignments for objects under *parent_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        assignments = []
        for child in parent.children():
            material = None
            for parm_name in MATERIAL_ASSIGN_PARMS:
                parm = child.parm(parm_name)
                if parm is not None:
                    try:
                        value = safe_parm_eval(parm)
                    except Exception:  # noqa: BLE001
                        value = None
                    if value:
                        material = value
                        break
            if material:
                assignments.append({"object": child.path(), "material": material})
        return skill_success(
            "Listed assignments",
            parent_path=parent.path(),
            count=len(assignments),
            assignments=assignments,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list assignments")


@skill_entry
def main(**kwargs) -> dict:
    return list_assignments(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
