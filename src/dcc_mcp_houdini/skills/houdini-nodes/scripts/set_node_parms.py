"""Set Houdini node parameters."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from _node_common import get_node, hou_import_error, node_summary, set_parm_value
from _node_common import press_buttons as _press_buttons
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def set_node_parms(
    node_path: str,
    parameters: Dict[str, Any],
    press_buttons: Optional[List[str]] = None,
) -> dict:
    """Set parameters on a Houdini node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        node = get_node(hou, node_path)
        changed = []
        for name, value in (parameters or {}).items():
            set_parm_value(node, name, value)
            changed.append(name)
        pressed = _press_buttons(node, press_buttons or [])
        return skill_success(
            "Updated Houdini node parameters",
            node=node_summary(node),
            parameters=changed,
            pressed_buttons=pressed,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set Houdini node parameters")


@skill_entry
def main(**kwargs) -> dict:
    return set_node_parms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
