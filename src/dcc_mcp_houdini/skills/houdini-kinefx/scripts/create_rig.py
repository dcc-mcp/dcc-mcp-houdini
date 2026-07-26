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
    node in the same geo container, KineFX Joint Capture Proximity and Joint
    Deform SOPs are wired for immediate skinning.

    Args:
        geo_path: Path to the Geometry SOP container (e.g. ``/obj/geo1``).
        rig_name: Name for the KineFX Skeleton SOP.
        joint_chain: List of joint definitions (name + translate).
        auto_capture: If True, capture and deform the mesh with KineFX SOPs.
        capture_mesh: Name of the mesh SOP node to capture (for auto_capture).
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        mesh_node = None
        if auto_capture:
            if not joint_chain:
                return skill_error("Joint chain required", "joint_chain is required when auto_capture is true")
            if not capture_mesh:
                return skill_error("Capture mesh required", "capture_mesh is required when auto_capture is true")
            geo = hou.node(geo_path)
            if geo is None:
                return skill_error("Geometry container not found", geo_path=geo_path)
            mesh_node = hou.node("{}/{}".format(geo.path(), capture_mesh))
            if mesh_node is None:
                return skill_error("Capture mesh not found", capture_mesh=capture_mesh, geo_path=geo_path)

        rig_node = get_or_create_rig(
            hou,
            geo_path=geo_path,
            rig_name=rig_name,
            joint_chain=joint_chain,
        )

        created_nodes = [rig_node.path()]

        if auto_capture:
            geo = get_node(hou, geo_path)
            rest_rig = geo.createNode("stash", node_name="rest_{}".format(rig_name))
            rest_stash = rest_rig.parm("stash")
            if rest_stash is None:
                raise RuntimeError("Rest Stash node has no stash parameter")
            rest_stash.set(hou.Geometry(rig_node.geometry()))
            rest_rig.cook(force=True)

            capture = geo.createNode("kinefx::jointcaptureproximity", node_name="capture_{}".format(rig_name))
            capture.setInput(0, mesh_node)
            capture.setInput(1, rest_rig)
            capture.setInput(2, rig_node)

            joint_deform = geo.createNode("kinefx::jointdeform", node_name="jointdeform_{}".format(rig_name))
            joint_deform.setInput(0, capture)
            joint_deform.setInput(1, rest_rig)
            joint_deform.setInput(2, rig_node)
            joint_deform.cook(force=True)

            rest_rig.moveToGoodPosition()
            capture.moveToGoodPosition()
            joint_deform.moveToGoodPosition()
            created_nodes.extend([rest_rig.path(), capture.path(), joint_deform.path()])

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
