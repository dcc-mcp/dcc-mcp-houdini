"""List parameters on a node that are keyframed or time-dependent."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _anim_common import get_node, parm_is_animated  # noqa: E402


def list_animated_parms(node_path: str) -> dict:
    """Return parameters on *node_path* that have keyframes or are time-dependent."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        animated = []
        for parm in node.parms():
            if not parm_is_animated(parm):
                continue
            try:
                keyframe_count = len(parm.keyframes())
            except Exception:  # noqa: BLE001
                keyframe_count = None
            animated.append({"name": parm.name(), "keyframe_count": keyframe_count})
        return skill_success(
            "Listed animated parameters",
            node_path=node.path(),
            count=len(animated),
            parameters=animated,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list animated parameters")


@skill_entry
def main(**kwargs) -> dict:
    return list_animated_parms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
