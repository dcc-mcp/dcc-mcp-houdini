"""Set the pose of a KineFX rig — joint transforms or overall rig pose."""

from __future__ import annotations

from typing import List, Optional

from _kinefx_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_rig_pose(
    rig_node: str,
    joint_index: Optional[int] = None,
    joint_name: Optional[str] = None,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> dict:
    """Set the pose transform on a joint in a KineFX rig.

    Target the joint by *joint_index* or *joint_name*.  When both are
    omitted, sets a uniform pose on the entire rig geometry (if applicable).

    The transform is applied to the point position/attributes on the rig SOP
    geometry.  For KineFX skeleton points, ``P`` (position), ``rot``, and
    ``scale`` point attributes are the standard pose controls.

    Args:
        rig_node: Path to the rig SOP node (e.g. ``/obj/geo1/rig1``).
        joint_index: Zero-based index of the joint point to modify.
        joint_name: Name attribute value of the joint to modify.
        translate: ``[x, y, z]`` translation to set.
        rotate: ``[rx, ry, rz]`` rotation in degrees.
        scale: ``[sx, sy, sz]`` scale factors.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, rig_node)
        geo = node.geometry()
        if geo is None:
            return skill_error("No geometry", "Rig node has no editable geometry")

        # Find the target point(s).
        target_pts = []
        if joint_index is not None:
            try:
                target_pts = [geo.iterPoints()[joint_index]]
            except IndexError:
                return skill_error(
                    "Joint index out of range",
                    joint_index=joint_index,
                    point_count=geo.floatListAttribValue("P") or 0,
                )
        elif joint_name is not None:
            name_attr = geo.findPointAttrib("name")
            if name_attr is None:
                return skill_error("No name attribute", "Rig geometry has no 'name' point attribute")
            for pt in geo.points():
                if pt.attribValue("name") == joint_name:
                    target_pts.append(pt)
                    break
            if not target_pts:
                return skill_error("Joint not found", joint_name=joint_name, rig_path=node.path())
        else:
            target_pts = geo.points()

        applied = {}
        for pt in target_pts:
            if translate is not None and len(translate) >= 3:
                pt.setPosition(hou.Vector3(float(translate[0]), float(translate[1]), float(translate[2])))
                applied["translate"] = translate
            if rotate is not None and len(rotate) >= 3:
                rot_attr = geo.findPointAttrib("rot")
                if rot_attr:
                    pt.setAttribValue(rot_attr, hou.Vector3(float(rotate[0]), float(rotate[1]), float(rotate[2])))
                else:
                    rot_attr = geo.addAttrib(hou.attribType.Point, "rot", hou.Vector3())
                    pt.setAttribValue(rot_attr, hou.Vector3(float(rotate[0]), float(rotate[1]), float(rotate[2])))
                applied["rotate"] = rotate
            if scale is not None and len(scale) >= 3:
                scale_attr = geo.findPointAttrib("scale")
                if scale_attr:
                    pt.setAttribValue(scale_attr, hou.Vector3(float(scale[0]), float(scale[1]), float(scale[2])))
                else:
                    scale_attr = geo.addAttrib(hou.attribType.Point, "scale", hou.Vector3())
                    pt.setAttribValue(scale_attr, hou.Vector3(float(scale[0]), float(scale[1]), float(scale[2])))
                applied["scale"] = scale

        return skill_success(
            "Set rig pose",
            rig_path=node.path(),
            joint_count=len(target_pts),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set rig pose")


@skill_entry
def main(**kwargs) -> dict:
    return set_rig_pose(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
