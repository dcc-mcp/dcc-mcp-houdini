"""Return the currently selected Houdini nodes."""

from __future__ import annotations

from _scene_edit_common import node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_selection() -> dict:
    """List the nodes Houdini currently reports as selected."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        nodes = [node_summary(n) for n in hou.selectedNodes()]
        return skill_success("Read current selection", nodes=nodes, count=len(nodes))
    except Exception as exc:
        return skill_exception(exc, message="Failed to read selection")


@skill_entry
def main(**kwargs) -> dict:
    return get_selection(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
