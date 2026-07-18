"""Create a KineFX skeleton rig with a joint chain."""

from __future__ import annotations

from typing import List, Optional

from _kinefx_common import get_node, get_or_create_rig  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_rig(
    geo_path: str,
    rig_name: str = "rig1",
    joint_chain: Optional[List[dict]] = None,
    auto_capture: bool = False,
    capture_mesh: Optional[str] = None,
) -> dict:
    """Create a KineFX skeleton rig inside *geo_path*.

    Builds a SOP-level skeleton with joint points.  Each entry in
    *joint_chain* specifies a joint:

    .. code-block:: json

        [
            {"name": "hip",   "translate": [0, 0, 0]},
            {"name": "spine", "translate": [0, 0.5, 0]},
            {"name": "head",  "translate": [0, 1.0, 0]}
        ]

    When *auto_capture* is ``True`` and *capture_mesh* names an existing SOP
    node in the same geo container, a ``bonedeform`` node is wired after the
    rig for immediate skinning.

    Args:
        geo_path: Path to the Geometry SOP container (e.g. ``/obj/geo1``).
        rig_name: Name for the rig null/container node.
        joint_chain: List of joint definitions (name + translate).
        auto_capture: If True, wire a bonedeform for immediate skinning.
        capture_mesh: Name of the mesh SOP node to capture (for auto_capture).
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rig_node = get_or_create_rig(
            hou,
            geo_path=geo_path,
            rig_name=rig_name,
            joint_chain=joint_chain,
        )

        created_nodes = [rig_node.path()]

        # Optional: auto-capture with a bonedeform node.
        if auto_capture and capture_mesh:
            geo = get_node(hou, geo_path)
            mesh_node = hou.node("{}/{}".format(geo.path(), capture_mesh))
            if mesh_node is not None:
                bone_deform = geo.createNode("bonedeform", node_name="bonedeform_{}".format(rig_name))
                bone_deform.setFirstInput(mesh_node)
                bone_deform.setInput(1, rig_node)
                bone_deform.moveToGoodPosition()
                created_nodes.append(bone_deform.path())

        return skill_success(
            "Created KineFX rig",
            rig_path=rig_node.path(),
            geo_path=geo_path,
            joint_count=len(joint_chain) if joint_chain else 0,
            auto_capture=auto_capture,
            created_nodes=created_nodes,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create KineFX rig")


@skill_entry
def main(**kwargs) -> dict:
    return create_rig(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
