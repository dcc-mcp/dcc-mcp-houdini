"""Set the pose of a KineFX rig — joint transforms or overall rig pose."""

from __future__ import annotations

from typing import List, Optional

from _kinefx_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _vector3(values: Optional[List[float]], label: str) -> Optional[tuple]:
    if values is None:
        return None
    if len(values) != 3:
        raise ValueError("{} must contain exactly 3 values".format(label))
    return tuple(float(value) for value in values)


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
    geometry. For KineFX skeleton points, world transforms are stored in
    ``P`` (position) and the ``transform`` matrix3 point attribute.

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
        if joint_index is not None and joint_index < 0:
            return skill_error("Joint index out of range", joint_index=joint_index)
        translate_values = _vector3(translate, "translate")
        rotate_values = _vector3(rotate, "rotate")
        scale_values = _vector3(scale, "scale")
        if translate_values is None and rotate_values is None and scale_values is None:
            return skill_error("No pose supplied", "Provide translate, rotate, and/or scale")

        node = get_node(hou, rig_node)
        cooked_geo = node.geometry()
        if cooked_geo is None:
            return skill_error("No geometry", "Rig node has no editable geometry")
        geo = hou.Geometry(cooked_geo)
        transform_attr = geo.findPointAttrib("transform")
        if (rotate_values is not None or scale_values is not None) and transform_attr is None:
            return skill_error("No transform attribute", "Rig geometry has no 'transform' matrix3 point attribute")

        # Find the target point(s).
        target_pts = []
        if joint_index is not None:
            try:
                target_pts = [geo.iterPoints()[joint_index]]
            except IndexError:
                return skill_error(
                    "Joint index out of range",
                    joint_index=joint_index,
                    point_count=len(geo.points()),
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
            if translate_values is not None:
                pt.setPosition(hou.Vector3(*translate_values))
                applied["translate"] = list(translate_values)
            if rotate_values is not None or scale_values is not None:
                current = hou.Matrix4(hou.Matrix3(pt.attribValue(transform_attr)))
                transform = hou.hmath.buildTransform(
                    {
                        "rotate": rotate_values if rotate_values is not None else current.extractRotates(),
                        "scale": scale_values if scale_values is not None else current.extractScales(),
                    }
                )
                pt.setAttribValue(transform_attr, hou.Matrix3(transform).asTuple())
                if rotate_values is not None:
                    applied["rotate"] = list(rotate_values)
                if scale_values is not None:
                    applied["scale"] = list(scale_values)

        stash = node.parm("stash")
        if stash is None:
            return skill_error("Unsupported rig node", "Rig node has no stash parameter")
        stash.set(geo)
        node.cook(force=True)

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
