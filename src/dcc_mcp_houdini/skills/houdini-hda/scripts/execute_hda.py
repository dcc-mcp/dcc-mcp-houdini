"""Instantiate and cook a Houdini Digital Asset."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from _hda_common import hou_import_error, node_summary, set_parm_value, validate_hda_path
from _hda_common import press_buttons as _press_buttons
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def execute_hda(
    operator_name: str,
    parent_path: str = "/obj",
    node_name: Optional[str] = None,
    hda_file: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    press_buttons: Optional[List[str]] = None,
    cook: bool = True,
    force_cook: bool = False,
) -> dict:
    """Install, create, configure, and optionally cook an HDA node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        installed_file = None
        if hda_file:
            hda_path = validate_hda_path(hda_file, must_exist=True)
            hou.hda.installFile(str(hda_path))
            installed_file = str(hda_path)

        parent = hou.node(parent_path)
        if parent is None:
            raise ValueError("Parent node not found: {}".format(parent_path))

        node = parent.createNode(operator_name, node_name=node_name)
        changed = []
        for name, value in (parameters or {}).items():
            set_parm_value(node, name, value)
            changed.append(name)
        pressed = _press_buttons(node, press_buttons or [])
        if cook:
            node.cook(force=force_cook)
        return skill_success(
            "Executed Houdini Digital Asset",
            installed_file=installed_file,
            node=node_summary(node),
            parameters=changed,
            pressed_buttons=pressed,
            cooked=cook,
            force_cook=force_cook,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to execute Houdini Digital Asset")


@skill_entry
def main(**kwargs) -> dict:
    return execute_hda(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
