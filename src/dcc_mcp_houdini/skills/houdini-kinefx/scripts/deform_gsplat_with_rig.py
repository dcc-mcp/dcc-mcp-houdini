"""Deform Gaussian Splat points with a KineFX skeleton."""

from __future__ import annotations

from typing import Optional

from _kinefx_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _set_first(node, names, value) -> Optional[str]:
    for name in names:
        parm = node.parm(name)
        if parm is not None:
            parm.set(value)
            return name
    return None


def deform_gsplat_with_rig(
    geo_path: str,
    captured_splats: str,
    rest_rig: str,
    animated_rig: str,
    output_name: str = "deformed_gsplats",
    skinning_method: str = "dual_quaternion",
    deform_normals: bool = True,
    preserve_capture_attributes: bool = True,
) -> dict:
    """Create a Joint Deform SOP that preserves GSplat orientation and scale.

    ``captured_splats`` must already contain ``boneCapture`` plus the GSplat
    ``P``, ``orient``, and ``scale`` or ``pscale`` point attributes. Joint
    Deform updates ``P`` and quaternion ``orient``; scale remains unchanged.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if skinning_method not in {"linear", "dual_quaternion", "blend"}:
            raise ValueError("skinning_method must be linear, dual_quaternion, or blend")

        geo = get_node(hou, geo_path)
        splats = get_node(hou, "{}/{}".format(geo.path(), captured_splats))
        rest = get_node(hou, "{}/{}".format(geo.path(), rest_rig))
        animated = get_node(hou, "{}/{}".format(geo.path(), animated_rig))

        geometry = splats.geometry()
        names = {attrib.name() for attrib in geometry.pointAttribs()}
        required = {"P", "boneCapture", "orient"}
        missing = sorted(required - names)
        if not ({"scale", "pscale"} & names):
            missing.append("scale_or_pscale")
        if missing:
            raise ValueError("captured_splats is missing: {}".format(", ".join(missing)))

        deform = geo.createNode("kinefx::jointdeform", node_name=output_name)
        deform.setInput(0, splats, 0)
        deform.setInput(1, rest, 0)
        deform.setInput(2, animated, 0)

        method_values = {"linear": "linear", "dual_quaternion": "dualquat", "blend": "blenddualquat"}
        method_parm = _set_first(deform, ("skinningmethod", "method"), method_values[skinning_method])
        attrs_parm = _set_first(deform, ("otherattribs", "otherattributes"), "orient")
        normals_parm = _set_first(deform, ("donormal", "deformnormals"), bool(deform_normals))
        delete_parm = _set_first(
            deform,
            ("deletecaptureattrib", "deletecaptureattribs", "deletecaptureattributes"),
            not bool(preserve_capture_attributes),
        )
        deform.moveToGoodPosition()

        return skill_success(
            "Created KineFX GSplat deformation",
            node_path=deform.path(),
            captured_splats=splats.path(),
            rest_rig=rest.path(),
            animated_rig=animated.path(),
            skinning_method=skinning_method,
            deformed_attributes=["P", "orient"] + (["N"] if deform_normals and "N" in names else []),
            preserved_attributes=sorted({"scale", "pscale"} & names),
            configured_parameters={
                "skinning_method": method_parm,
                "other_attributes": attrs_parm,
                "deform_normals": normals_parm,
                "delete_capture_attributes": delete_parm,
            },
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create KineFX GSplat deformation")


@skill_entry
def main(**kwargs) -> dict:
    return deform_gsplat_with_rig(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
