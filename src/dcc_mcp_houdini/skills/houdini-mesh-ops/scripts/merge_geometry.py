"""Append a Merge SOP joining multiple input SOP streams."""

from __future__ import annotations

from typing import List, Optional

from _mesh_common import get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def merge_geometry(input_paths: List[str], node_name: Optional[str] = None) -> dict:
    """Create a Merge SOP in the first input's parent, wiring all inputs."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if not input_paths:
        return skill_error("No inputs", "Provide at least one input node path")

    try:
        sources = [get_node(hou, p) for p in input_paths]
        parent = sources[0].parent()
        if parent is None:
            return skill_error("No parent network", "First input has no parent network")
        merge = parent.createNode("merge", node_name=node_name)
        for index, source in enumerate(sources):
            merge.setInput(index, source)
        if hasattr(merge, "moveToGoodPosition"):
            try:
                merge.moveToGoodPosition()
            except Exception:  # noqa: BLE001
                pass
        if hasattr(merge, "setDisplayFlag"):
            merge.setDisplayFlag(True)
        return skill_success(
            "Created merge SOP",
            input_paths=[s.path() for s in sources],
            node=node_summary(merge),
            input_count=len(sources),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create merge SOP")


@skill_entry
def main(**kwargs) -> dict:
    return merge_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
