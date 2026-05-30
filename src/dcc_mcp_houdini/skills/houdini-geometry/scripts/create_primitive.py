"""Create a common SOP primitive inside a SOP network."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _geo_common import get_node  # noqa: E402

# Friendly primitive name -> SOP node type name.
_PRIMITIVES = {
    "box": "box",
    "sphere": "sphere",
    "grid": "grid",
    "tube": "tube",
    "curve": "curve",
    "null": "null",
    "output": "output",
}


def create_primitive(
    parent_path: str,
    primitive: str,
    node_name: Optional[str] = None,
    set_display: bool = True,
) -> dict:
    """Create a ``primitive`` SOP under *parent_path* (a SOP network)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    sop_type = _PRIMITIVES.get(primitive.lower())
    if sop_type is None:
        return skill_error(
            "Unsupported primitive",
            "primitive must be one of: {}".format(", ".join(sorted(_PRIMITIVES))),
            requested=primitive,
        )
    try:
        parent = get_node(hou, parent_path)
        node = parent.createNode(sop_type, node_name=node_name)
        if set_display and hasattr(node, "setDisplayFlag"):
            node.setDisplayFlag(True)
        return skill_success(
            "Created SOP primitive",
            parent_path=parent.path(),
            node_path=node.path(),
            node_name=node.name(),
            primitive=primitive.lower(),
            sop_type=sop_type,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create SOP primitive")


@skill_entry
def main(**kwargs) -> dict:
    return create_primitive(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
