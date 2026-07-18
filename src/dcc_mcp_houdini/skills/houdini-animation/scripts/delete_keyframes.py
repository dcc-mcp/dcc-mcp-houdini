"""Delete keyframes on a node parameter (all, or within a frame range)."""

from __future__ import annotations

from typing import List, Optional

from _anim_common import get_node, get_parm  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def delete_keyframes(
    node_path: str,
    parm_name: str,
    frame_range: Optional[List[float]] = None,
) -> dict:
    """Delete keyframes on ``node_path/parm_name``.

    With no ``frame_range`` all keyframes are removed; otherwise only those
    whose frame falls within ``[start, end]`` inclusive.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parm = get_parm(node, parm_name)
        if frame_range is None:
            before = len(parm.keyframes())
            parm.deleteAllKeyframes()
            return skill_success(
                "Deleted all keyframes",
                node_path=node.path(),
                parm=parm_name,
                deleted=before,
            )
        start, end = float(frame_range[0]), float(frame_range[1])
        removed = 0
        for kf in list(parm.keyframes()):
            frame = kf.frame()
            if start <= frame <= end:
                parm.deleteKeyframeAtFrame(frame)
                removed += 1
        return skill_success(
            "Deleted keyframes in range",
            node_path=node.path(),
            parm=parm_name,
            frame_range=[start, end],
            deleted=removed,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to delete keyframes")


@skill_entry
def main(**kwargs) -> dict:
    return delete_keyframes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
