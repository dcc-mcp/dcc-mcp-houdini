"""Assign a Houdini material node to a target node."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _material_common import get_node, hou_import_error, node_summary


def assign_material(
    target_node_path: str,
    material_node_path: str,
    parameter_name: str = "shop_materialpath",
) -> dict:
    """Assign *material_node_path* by setting *parameter_name* on the target."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        target = get_node(hou, target_node_path)
        material = get_node(hou, material_node_path)
        parm = target.parm(parameter_name)
        if parm is None:
            raise ValueError("Parameter {!r} not found on {}".format(parameter_name, target.path()))
        parm.set(material.path())
        return skill_success(
            "Assigned Houdini material",
            target=node_summary(target),
            material=node_summary(material),
            parameter_name=parameter_name,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to assign Houdini material")


@skill_entry
def main(**kwargs) -> dict:
    return assign_material(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
