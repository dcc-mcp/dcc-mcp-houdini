"""Add a spare parameter to a Houdini node."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _parm_common import get_node  # noqa: E402


def _build_template(hou, parm_type: str, name: str, label: str, num_components: int):
    """Build a parm template for a supported type, or return None."""
    label = label or name
    if parm_type == "float":
        return hou.FloatParmTemplate(name, label, num_components)
    if parm_type == "int":
        return hou.IntParmTemplate(name, label, num_components)
    if parm_type == "string":
        return hou.StringParmTemplate(name, label, num_components)
    if parm_type == "toggle":
        return hou.ToggleParmTemplate(name, label)
    return None


def add_spare_parm(
    node_path: str,
    name: str,
    parm_type: str = "float",
    label: Optional[str] = None,
    num_components: int = 1,
) -> dict:
    """Add a spare parameter of ``parm_type`` (float/int/string/toggle)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        template = _build_template(hou, parm_type, name, label or name, num_components)
        if template is None:
            return skill_error(
                "Unsupported parameter type",
                "parm_type must be one of: float, int, string, toggle",
                requested=parm_type,
            )
        node.addSpareParmTuple(template)
        return skill_success(
            "Added spare parameter",
            node_path=node.path(),
            name=name,
            parm_type=parm_type,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to add spare parameter")


@skill_entry
def main(**kwargs) -> dict:
    return add_spare_parm(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
