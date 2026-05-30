"""List material/shader nodes under a material network (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _lookdev_common import get_node  # noqa: E402


def list_materials(parent_path: str = "/mat") -> dict:
    """Return shader/material nodes under *parent_path* (e.g. /mat or a matnet)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        materials = []
        for child in parent.children():
            type_obj = child.type()
            category = type_obj.category().name() if hasattr(type_obj, "category") else None
            materials.append(
                {
                    "path": child.path(),
                    "name": child.name(),
                    "type": type_obj.name(),
                    "category": category,
                }
            )
        return skill_success(
            "Listed materials",
            parent_path=parent.path(),
            count=len(materials),
            materials=materials,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list materials")


@skill_entry
def main(**kwargs) -> dict:
    return list_materials(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
