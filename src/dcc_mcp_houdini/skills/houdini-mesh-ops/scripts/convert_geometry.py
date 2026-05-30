"""Append a Convert SOP to change the geometry primitive type."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _mesh_common import get_node, make_downstream_sop, node_summary, set_parm_if_exists  # noqa: E402

# Friendly target type -> convert SOP 'totype' menu token.
_TO_TYPE = {
    "polygons": "poly",
    "poly": "poly",
    "mesh": "mesh",
    "nurbs": "nurbs",
    "bezier": "bezier",
    "subdivision": "subdiv",
    "subdiv": "subdiv",
}


def convert_geometry(
    input_path: str,
    to_type: str = "polygons",
    node_name: Optional[str] = None,
) -> dict:
    """Create a Convert SOP downstream of *input_path* set to ``to_type``."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    token = _TO_TYPE.get(to_type.lower())
    if token is None:
        return skill_error(
            "Unsupported target type",
            "to_type must be one of: {}".format(", ".join(sorted(set(_TO_TYPE)))),
            requested=to_type,
        )
    try:
        source = get_node(hou, input_path)
        convert = make_downstream_sop(source, "convert", node_name)
        set_parm_if_exists(convert, "totype", token)
        return skill_success(
            "Created convert SOP",
            input_path=source.path(),
            node=node_summary(convert),
            to_type=token,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create convert SOP")


@skill_entry
def main(**kwargs) -> dict:
    return convert_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
