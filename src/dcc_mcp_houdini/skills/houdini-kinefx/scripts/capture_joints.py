"""Capture skinning weights from a KineFX skeleton onto a geometry mesh."""

from __future__ import annotations

from typing import Optional

from _kinefx_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def capture_joints(
    geo_path: str,
    mesh_name: str,
    rig_name: str,
    method: str = "proximity",
    max_joints: int = 4,
    falloff: float = 1.0,
    output_name: Optional[str] = None,
) -> dict:
    """Capture skinning weights from *rig_name* onto *mesh_name* in *geo_path*.

    Wires a ``captureproximity`` (or ``bonecapture``) SOP node between the
    mesh and rig, producing ``boneCapture`` point attributes that
    ``bonedeform`` reads at deformation time.

    Args:
        geo_path: Path to the Geometry SOP container.
        mesh_name: Name of the mesh SOP node to capture onto.
        rig_name: Name of the rig SOP node (skeleton source).
        method: Capture method — ``proximity``, ``bones``, or ``heat``.
        max_joints: Maximum number of influencing joints per point.
        falloff: Falloff distance multiplier for capture radius.
        output_name: Name for the capture SOP node (auto-generated if omitted).
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        geo = get_node(hou, geo_path)
        mesh_node = get_node(hou, "{}/{}".format(geo.path(), mesh_name))
        rig_node = get_node(hou, "{}/{}".format(geo.path(), rig_name))

        # Choose capture node type.
        method_map = {
            "proximity": "captureproximity",
            "bones": "bonecapture",
            "heat": "captureproximity",  # fallback: heat diffusion via proximity
        }
        node_type = method_map.get(method.lower(), "captureproximity")

        capture_name = output_name or "capture_{}".format(rig_name)
        capture_node = geo.createNode(node_type, node_name=capture_name)

        # Wire: mesh in port 0, skeleton (rest geometry) in port 1.
        capture_node.setFirstInput(mesh_node)
        try:
            capture_node.setInput(1, rig_node, 0)
        except Exception:  # noqa: BLE001
            pass

        # Configure capture parameters.
        if node_type == "captureproximity":
            try:
                capture_node.parm("maxpoints").set(max_joints)
            except Exception:  # noqa: BLE001
                pass
            try:
                capture_node.parm("falloff").set(float(falloff))
            except Exception:  # noqa: BLE001
                pass

        capture_node.moveToGoodPosition()

        return skill_success(
            "Captured joints",
            capture_node_path=capture_node.path(),
            geo_path=geo_path,
            mesh_name=mesh_name,
            rig_name=rig_name,
            method=method,
            max_joints=max_joints,
            falloff=falloff,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to capture joints")


@skill_entry
def main(**kwargs) -> dict:
    return capture_joints(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
