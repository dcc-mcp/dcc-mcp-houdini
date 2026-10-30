"""Return an explicit biped joint-name mapping between two naming conventions.

Pure tool (no ``hou`` import). The map is consumed by
``configure_biped_retarget`` / ``build_retarget_motion_mixer`` to author a
``retarget_joint`` point attribute, enabling KineFX Map Points / Full Body IK to
retarget skeletons whose joints are named differently (Mixamo, 3ds Max Biped,
Unreal Mannequin, generic FBX).
"""

from __future__ import annotations

from _character_common import CONVENTIONS
from _character_common import biped_joint_map as _map
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def biped_joint_map(
    source_convention: str = "mixamo",
    target_convention: str = "kinefx",
) -> dict:
    """Return ``source_name -> target_name`` pairs for a biped retarget.

    Args:
        source_convention: naming of the mocap/source skeleton.
        target_convention: naming of the target biped template.
    """
    for label, value in (("source_convention", source_convention), ("target_convention", target_convention)):
        if value not in CONVENTIONS:
            return skill_error(
                "Unknown naming convention",
                "{} must be one of {}".format(label, ", ".join(CONVENTIONS)),
                label=label,
                value=value,
            )
    result = _map(source_convention, target_convention)
    return skill_success(
        "Biped joint map",
        schema="dcc-mcp-houdini.biped-joint-map/v1",
        source_convention=result["source_convention"],
        target_convention=result["target_convention"],
        joint_count=result["joint_count"],
        pairs=result["pairs"],
        reverse_pairs=result["reverse_pairs"],
        usage=(
            "Set a point string attribute 'retarget_joint' on the source skeleton "
            "to pairs[source_joint_name] and on the target to the matching value, "
            "then use kinefx::mappoints / kinefx::fullbodyik with mapusing=attribute."
        ),
    )


@skill_entry
def main(**kwargs) -> dict:
    return biped_joint_map(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
