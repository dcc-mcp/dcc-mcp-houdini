"""Loft ordered cross-section SOPs through a verified Skin SOP."""

from __future__ import annotations

from typing import List, Optional

from _mesh_common import cook_readback, geometry_readback, get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def loft_sections(sections: List[str], node_name: Optional[str] = None) -> dict:
    """Connect ordered section SOPs to Skin and verify cooked output."""
    if not isinstance(sections, list) or not 2 <= len(sections) <= 64:
        return skill_error("Invalid loft sections", "sections must contain 2 through 64 node paths")
    if any(not isinstance(path, str) or not path for path in sections):
        return skill_error("Invalid loft sections", "every section must be a non-empty node path")
    if len(set(sections)) != len(sections):
        return skill_error("Invalid loft sections", "section node paths must be unique")
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = []
    try:
        sources = [get_node(hou, path) for path in sections]
        parent = sources[0].parent()
        if parent is None:
            raise ValueError("First loft section has no parent SOP network")
        if any(source.parent() is not parent for source in sources[1:]):
            raise ValueError("All loft sections must share one parent SOP network")
        before = geometry_readback(sources[0])
        merge = parent.createNode("merge")
        created.append(merge)
        for index, source in enumerate(sources):
            merge.setInput(index, source)
        if hasattr(merge, "moveToGoodPosition"):
            merge.moveToGoodPosition()
        merge_readback = cook_readback(merge, require_change=False)

        skin = parent.createNode("skin", node_name=node_name)
        created.append(skin)
        skin.setInput(0, merge)
        if hasattr(skin, "moveToGoodPosition"):
            skin.moveToGoodPosition()
        if hasattr(skin, "setDisplayFlag"):
            skin.setDisplayFlag(True)
        readback = cook_readback(skin, before=before)
        readback["merge"] = merge_readback
        return skill_success(
            "Created and verified Skin SOP loft",
            sections=[source.path() for source in sources],
            merge_node=node_summary(merge),
            node=node_summary(skin),
            readback=readback,
        )
    except Exception:  # noqa: BLE001
        for node in reversed(created):
            try:
                node.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_error(
            "Failed to create verified Skin SOP loft",
            "Houdini rejected the bounded loft transaction",
        )


@skill_entry
def main(**kwargs) -> dict:
    return loft_sections(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
