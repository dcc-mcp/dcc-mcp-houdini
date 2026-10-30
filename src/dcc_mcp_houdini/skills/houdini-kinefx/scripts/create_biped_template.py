"""Create a standard humanoid Biped KineFX skeleton template.

Fills workflow stage 3 (Biped template). Unlike ``create_rig`` (a generic joint
chain) and ``create_insect_rig`` (an anatomy-aware honeybee), this builds a
stable 22-joint humanoid biped whose names come from a configurable naming
convention (kinefx/biped/mixamo/unreal/fbx). The same joint map feeds retarget,
rig inversion and the APEX FBX biped template.
"""

from __future__ import annotations

from _character_common import CONVENTIONS, biped_chain
from _kinefx_common import get_geo_container, get_or_create_rig
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_biped_template(
    geo_path: str,
    rig_name: str = "biped",
    convention: str = "kinefx",
    height: float = 1.7,
    ground_z: float = 0.0,
) -> dict:
    """Create a humanoid biped KineFX skeleton SOP inside *geo_path*.

    Args:
        geo_path: Geometry SOP container path (e.g. ``/obj/character1``).
        rig_name: Name of the KineFX skeleton SOP node.
        convention: Joint naming convention (kinefx/biped/mixamo/unreal/fbx).
        height: Target character height in world units.
        ground_z: Height of the ground plane the feet rest on.
    """
    if convention not in CONVENTIONS:
        return skill_error(
            "Unknown naming convention",
            "convention must be one of {}".format(", ".join(CONVENTIONS)),
            convention=convention,
        )
    if not isinstance(geo_path, str) or not geo_path.strip():
        return skill_error("Invalid geo_path", "geo_path must be a non-empty string")
    if height <= 0:
        return skill_error("Invalid height", "height must be positive", height=height)

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        chain = biped_chain(height, convention, ground_z)
        geo = get_geo_container(hou, geo_path)
        rig = get_or_create_rig(
            hou,
            geo_path=geo.path(),
            rig_name=rig_name,
            joint_chain=chain["joint_chain"],
        )
        rig.cook(force=True)
        return skill_success(
            "Created humanoid Biped template",
            rig_path=rig.path(),
            geo_path=geo.path(),
            convention=convention,
            height=height,
            ground_z=ground_z,
            joint_count=len(chain["joint_names"]),
            joint_names=chain["joint_names"],
            support_joint_names=chain["support_joint_names"],
            canonical_keys=chain["canonical_keys"],
            parent_indices=chain["parent_indices"],
        )
    except Exception as exc:  # noqa: BLE001
        return skill_exception(exc, message="Failed to create Biped template")


@skill_entry
def main(**kwargs) -> dict:
    return create_biped_template(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
