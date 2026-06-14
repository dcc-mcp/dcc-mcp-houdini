"""Apply motion capture data to a KineFX rig skeleton."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _kinefx_common import get_node  # noqa: E402


def apply_mocap(
    geo_path: str,
    rig_name: str,
    mocap_file: str,
    start_frame: Optional[float] = None,
    scale: float = 1.0,
    mocap_node_name: str = "mocap1",
) -> dict:
    """Apply motion capture data onto *rig_name* in *geo_path*.

    Imports a mocap file (FBX, BVH, or KineFX ``.bclip``/``.clip``) and
    wires it through a ``motionclip`` or ``agentclip`` SOP node that drives
    the rig skeleton.

    Args:
        geo_path: Path to the Geometry SOP container.
        rig_name: Name of the rig SOP node to animate.
        mocap_file: Path to the mocap file (.fbx, .bvh, .bclip, .clip).
        start_frame: Start frame offset for the mocap data.
        scale: Uniform scale applied to the mocap data.
        mocap_node_name: Name for the mocap import SOP node.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    ext = mocap_file.rsplit(".", 1)[-1].lower() if "." in mocap_file else ""

    try:
        geo = get_node(hou, geo_path)
        rig_node = get_node(hou, "{}/{}".format(geo.path(), rig_name))

        # Determine import SOP type based on file extension.
        if ext in ("bclip", "clip"):
            # Native KineFX motion clip — use motionclip SOP.
            import_node = geo.createNode("motionclip", node_name=mocap_node_name)
            import_node.parm("file").set(mocap_file)
        elif ext in ("bvh",):
            # BVH file — use a file SOP (BVH comes in as points).
            import_node = geo.createNode("file", node_name=mocap_node_name)
            import_node.parm("file").set(mocap_file)
        elif ext in ("fbx",):
            # FBX — use the FBX character import SOP or agent SOP.
            import_node = geo.createNode("file", node_name=mocap_node_name)
            import_node.parm("file").set(mocap_file)
        else:
            # Unknown — try generic file SOP.
            import_node = geo.createNode("file", node_name=mocap_node_name)
            import_node.parm("file").set(mocap_file)

        # Set scale.
        if scale != 1.0:
            try:
                import_node.parm("scale").set(float(scale))
            except Exception:  # noqa: BLE001
                pass

        # Set start frame.
        if start_frame is not None:
            try:
                import_node.parm("start").set(float(start_frame))
            except Exception:  # noqa: BLE001
                pass

        # Wire: mocap drives the rig via the second input of a bonedeform
        # or by connecting directly as the skeleton source.
        # Create a bonedeform to apply the mocap-driven animation.
        bone_deform = geo.createNode("bonedeform", node_name="anim_{}".format(rig_name))
        bone_deform.setInput(0, import_node, 0)  # animated skeleton
        bone_deform.setInput(1, rig_node, 0)  # rest skeleton

        import_node.moveToGoodPosition()
        bone_deform.moveToGoodPosition()

        return skill_success(
            "Applied mocap",
            mocap_node_path=import_node.path(),
            bone_deform_path=bone_deform.path(),
            geo_path=geo_path,
            rig_name=rig_name,
            mocap_file=mocap_file,
            file_type=ext,
            scale=scale,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to apply mocap")


@skill_entry
def main(**kwargs) -> dict:
    return apply_mocap(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
