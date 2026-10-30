"""Configure a single-source biped motion retarget (workflow stage 4).

Builds the Houdini 22 KineFX contract Rig Match Pose -> Map Points -> Full Body
IK between a source mocap skeleton and a target Biped template. Unlike
``build_retarget_motion_mixer`` (which mixes two or more identically-named
clips), this tool accepts an explicit ``joint_map`` so a differently-named
source skeleton (Mixamo, 3ds Max Biped, Unreal) can be mapped onto the target.
"""

from __future__ import annotations

from typing import Any, Optional

from _character_common import CONVENTIONS
from _character_common import biped_joint_map as _map
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _set_if_present(node: Any, name: str, value: Any) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def _cook_failures(nodes) -> list:
    failures = []
    for node in nodes:
        node.cook(force=True)
        errors = list(node.errors())
        warnings = list(node.warnings())
        if errors or warnings:
            failures.append({"path": node.path(), "errors": errors, "warnings": warnings})
    return failures


def _has_point_attrib(node: Any, attribute: str) -> bool:
    """Return True only when *node* geometry actually carries a point attribute.

    Attribute-mode retargeting (``automapinline=0``/``mapusing=1``) reads
    ``mapping_attribute`` values off the source skeleton points. If the caller
    never authored them, Map Points has nothing to map and the build must not
    be reported as validated.
    """
    try:
        geometry = node.geometry()
    except Exception:  # noqa: BLE001 - a non-cookable source is "missing"
        return False
    if geometry is None:
        return False
    try:
        return geometry.findPointAttrib(attribute) is not None
    except Exception:  # noqa: BLE001
        return False


def configure_biped_retarget(
    geo_path: str,
    target_skeleton: str,
    source_skeleton: str,
    source_convention: Optional[str] = None,
    target_convention: Optional[str] = None,
    joint_map: Optional[dict] = None,
    mapping_attribute: str = "retarget_joint",
    node_prefix: str = "dcc_mcp_biped_retarget",
) -> dict:
    """Build a single-source biped retarget chain in *geo_path*.

    Exactly one of ``joint_map`` or ``(source_convention, target_convention)``
    should describe the mapping. When both conventions are given the standard
    biped naming map is used; an explicit ``joint_map`` (source name -> target
    name) takes precedence.

    Args:
        geo_path: Geometry SOP container holding both skeletons.
        target_skeleton: Path to the target Biped skeleton SOP.
        source_skeleton: Path to the source mocap skeleton SOP.
        source_convention: Naming convention of the source skeleton.
        target_convention: Naming convention of the target skeleton.
        joint_map: Explicit ``{source_name: target_name}`` mapping.
        mapping_attribute: Point attribute used by Map Points / Full Body IK.
        node_prefix: Prefix for created nodes.
    """
    if not isinstance(geo_path, str) or not geo_path.strip():
        return skill_error("Invalid geo_path", "geo_path must be a non-empty string")
    if not isinstance(target_skeleton, str) or not isinstance(source_skeleton, str):
        return skill_error("Invalid skeleton paths", "both skeleton paths must be strings")

    mapping = None
    if joint_map:
        if not isinstance(joint_map, dict) or not joint_map:
            return skill_error("Invalid joint_map", "joint_map must be a non-empty object")
        mapping = dict(joint_map)
    elif source_convention and target_convention:
        for label, value in (("source_convention", source_convention), ("target_convention", target_convention)):
            if value not in CONVENTIONS:
                return skill_error(
                    "Unknown naming convention",
                    "{} must be one of {}".format(label, ", ".join(CONVENTIONS)),
                    label=label,
                    value=value,
                )
        mapping = _map(source_convention, target_convention)["pairs"]
    else:
        return skill_error(
            "No mapping provided",
            "Provide joint_map or both source_convention and target_convention",
        )

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        container = hou.node(geo_path)
        if container is None:
            return skill_error("Geometry container not found", "container_not_found", geo_path=geo_path)
        target = hou.node(target_skeleton)
        source = hou.node(source_skeleton)
        if target is None or source is None:
            return skill_error(
                "Skeleton not found",
                "target or source skeleton path is invalid",
                target_skeleton=target_skeleton,
                source_skeleton=source_skeleton,
            )

        # B1: this tool always builds an explicit (attribute-mode) retarget, so
        # the source skeleton must already carry mapping_attribute point values
        # (authored from joint_map: source joint name -> target joint name).
        # Verify before building; error instead of reporting a "configured"
        # success when the mapping cannot take effect. Consistent with the
        # explicit-map path in build_retarget_motion_mixer (reviewed F2 fix).
        if not _has_point_attrib(source, mapping_attribute):
            return skill_error(
                "Mapping attribute missing on source skeleton",
                "mapping_attribute_missing",
                mapping_attribute=mapping_attribute,
                source_skeleton=source.path(),
                next_tools=["biped_joint_map", "configure_biped_retarget"],
                hint=(
                    "Author the mapping_attribute point values on the source "
                    "skeleton from joint_map before configuring the retarget."
                ),
            )

        def create(type_name, name):
            node = container.createNode(type_name, node_name="{}_{}".format(node_prefix, name))
            node.setComment("DCC-MCP typed biped retarget")
            return node

        created = []

        # The source skeleton is expected to carry the mapping_attribute point
        # values (verified above). These Map Points / Full Body IK nodes consume
        # that attribute in attribute-mapping mode; this tool does not author
        # the attribute itself (see biped_joint_map / hint above).
        target_map = create("kinefx::mappoints", "target_map")
        target_map.setInput(0, target)
        _set_if_present(target_map, "mappingattrib", mapping_attribute)
        _set_if_present(target_map, "invert", 0)

        match = create("kinefx::rigmatchpose", "match")
        match.setInput(0, target_map, 0)
        match.setInput(1, source)
        _set_if_present(match, "bboxmatch", 1)

        mapping_node = create("kinefx::mappoints", "map")
        mapping_node.setInput(0, match, 0)
        mapping_node.setInput(1, match, 1)
        _set_if_present(mapping_node, "mappingattrib", mapping_attribute)
        _set_if_present(mapping_node, "referenceattrib", "name")
        _set_if_present(mapping_node, "automapinline", 0)
        _set_if_present(mapping_node, "mapusing", 1)

        solve = create("kinefx::fullbodyik", "solve")
        solve.setInput(0, mapping_node, 0)
        solve.setInput(1, mapping_node, 1)
        _set_if_present(solve, "mapusing", 1)
        _set_if_present(solve, "mappingattribname", mapping_attribute)
        _set_if_present(solve, "attribtomatch", "name")
        _set_if_present(solve, "computelocaltransform", 1)

        created.extend((target_map, match, mapping_node, solve))
        failures = _cook_failures(created)
        try:
            container.layoutChildren()
        except Exception:  # noqa: BLE001
            pass

        return skill_success(
            "Configured single-source biped retarget",
            geo_path=container.path(),
            target_skeleton=target.path(),
            source_skeleton=source.path(),
            mapping_attribute=mapping_attribute,
            mapping_attribute_verified=True,
            joint_map=mapping,
            mapped_joint_count=len(mapping),
            sop_output=solve.path(),
            created_nodes=[node.path() for node in created],
            cook_failures=failures,
            validated=not failures,
            next_tools=["build_retarget_motion_mixer", "invert_rig"],
        )
    except Exception as exc:  # noqa: BLE001
        return skill_exception(exc, message="Failed to configure biped retarget")


@skill_entry
def main(**kwargs) -> dict:
    return configure_biped_retarget(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
