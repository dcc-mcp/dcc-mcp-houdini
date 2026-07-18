"""Import or create a motion clip CHOP in a CHOP network."""

from __future__ import annotations

from typing import Optional

from _chops_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_motionclip(
    network_path: str,
    node_name: str = "motionclip1",
    clip_file: Optional[str] = None,
    start_frame: Optional[float] = None,
) -> dict:
    """Create a MotionClip CHOP inside *network_path*.

    The MotionClip CHOP is the standard way to import character animation
    clips (``.bclip`` / ``.clip``) into the CHOP context.

    Args:
        network_path: Path to the CHOP network (e.g. ``/ch/chopnet1``).
        node_name: Name for the new MotionClip node.
        clip_file: Optional path to a ``.bclip``/``.clip`` file to load.
        start_frame: Optional start frame override for the clip.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        network = get_node(hou, network_path)
        node = network.createNode("motionclip", node_name=node_name)

        applied: dict = {}
        if clip_file:
            node.parm("file").set(clip_file)
            applied["clip_file"] = clip_file
        if start_frame is not None:
            node.parm("start").set(float(start_frame))
            applied["start_frame"] = float(start_frame)

        node.moveToGoodPosition()

        return skill_success(
            "Created MotionClip CHOP",
            node_path=node.path(),
            node_name=node.name(),
            network_path=network_path,
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create MotionClip CHOP")


@skill_entry
def main(**kwargs) -> dict:
    return create_motionclip(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
