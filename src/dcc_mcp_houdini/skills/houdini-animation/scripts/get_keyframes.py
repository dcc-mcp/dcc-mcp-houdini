"""List keyframes on a node parameter."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _anim_common import get_node, get_parm, keyframe_dict  # noqa: E402


def get_keyframes(node_path: str, parm_name: str) -> dict:
    """Return the keyframes on ``node_path/parm_name``."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parm = get_parm(node, parm_name)
        keyframes = [keyframe_dict(kf) for kf in parm.keyframes()]
        return skill_success(
            "Listed keyframes",
            node_path=node.path(),
            parm=parm_name,
            count=len(keyframes),
            keyframes=keyframes,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list keyframes")


@skill_entry
def main(**kwargs) -> dict:
    return get_keyframes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
