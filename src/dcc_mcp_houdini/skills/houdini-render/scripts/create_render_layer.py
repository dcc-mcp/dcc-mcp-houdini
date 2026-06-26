"""Create a render layer / AOV pass setup in Solaris (/stage) or a ROP network."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import get_node, node_summary, set_first_parm  # noqa: E402


def create_render_layer(
    name: str,
    parent_path: str = "/stage",
    aovs: Optional[list] = None,
    purpose: str = "beauty",
) -> dict:
    """Create a render layer (RenderVar / RenderProduct) under *parent_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        is_solaris = parent_path.startswith("/stage")

        if is_solaris:
            # Solaris: create a Render Product LOP
            layer = parent.createNode("renderproduct", node_name=name)
            set_first_parm(layer, ("productname",), name)
            if purpose:
                set_first_parm(layer, ("producttype",), purpose)
            # Create render vars (AOVs) as children
            created_aovs = []
            if aovs:
                for aov_name in aovs:
                    rv = layer.createNode("rendervar", node_name=aov_name)
                    set_first_parm(rv, ("sourceName", "sourcename"), aov_name)
                    set_first_parm(rv, ("sourceType", "sourcetype"), "raw")
                    created_aovs.append({"name": aov_name, "path": rv.path()})
            return skill_success(
                "Created render layer (Solaris)",
                node=node_summary(layer),
                purpose=purpose,
                aovs=created_aovs,
                context="solaris",
            )
        else:
            # Traditional: create a ROP network or merge node
            layer = parent.createNode("merge", node_name=name)
            return skill_success(
                "Created render layer placeholder (ROP)",
                node=node_summary(layer),
                purpose=purpose,
                context="rop",
                hint="Use houdini_nodes to add ROP drivers inside this network",
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create render layer")


@skill_entry
def main(**kwargs) -> dict:
    return create_render_layer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
