"""Build a Houdini 22 KineFX retarget and APEX Motion Mixer network."""

from __future__ import annotations

from typing import Any

from _character_common import CONVENTIONS
from _character_common import biped_joint_map as _biped_map
from _kinefx_common import RequiresHoudini22, capability_create_node, get_node, guarded_cook_failures
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _set_if_present(node: Any, name: str, value: Any) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def _create(container: Any, type_name: str, name: str) -> Any:
    # capability_create_node converts a missing H22 node type (Houdini 20.5/21)
    # into RequiresHoudini22 so the tool can degrade gracefully instead of
    # raising an uncaught "Invalid node type name" / hou.OperationFailed.
    node = capability_create_node(container, type_name, name)
    node.setComment("DCC-MCP typed Houdini 22 animation workflow")
    return node


def _has_point_attrib(node: Any, attribute: str) -> bool:
    """Return True only when *node* geometry actually carries a point attribute.

    Explicit-attribute retargeting reads ``mapping_attribute`` values off the
    source skeleton points. If the caller never authored them, Map Points has
    nothing to map, so the tool must not report a validated build.
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


def build_retarget_motion_mixer(
    geo_path: str,
    target_skeleton: str,
    source_skeletons: list[str],
    character_name: str = "character",
    clip_names: list[str] | None = None,
    start_frame: int = 1,
    end_frame: int = 96,
    mapping_attribute: str = "retarget_joint",
    node_prefix: str = "dcc_mcp_retarget",
    add_secondary_motion: bool = True,
    joint_map: dict | None = None,
    source_convention: str | None = None,
    target_convention: str | None = None,
) -> dict:
    """Create and cook a retarget, MotionClip, APEX, and Motion Mixer chain.

    ``target_skeleton`` and every item in ``source_skeletons`` are existing SOP
    paths. Source skeletons should be time-dependent KineFX skeleton geometry.
    At least two sources are required so the generated Motion Mixer has clips to
    combine.

    Enhancement (E1): pass ``joint_map`` (``{source_name: target_name}``) or both
    ``source_convention``/``target_convention`` to retarget across differently
    named biped skeletons. When a map is supplied, mapping switches from
    auto-by-name to explicit-attribute mode; the caller authors the
    ``mapping_attribute`` point values from the returned ``joint_map`` (see
    ``biped_joint_map`` / ``configure_biped_retarget``). With no map the original
    auto-mapping behavior is unchanged.
    """
    if len(source_skeletons) < 2:
        return skill_error(
            "At least two source skeletons are required",
            "source_skeletons must contain two or more SOP paths",
        )
    if end_frame < start_frame:
        return skill_error("Invalid frame range", "end_frame must be >= start_frame")

    explicit_map = None
    if joint_map:
        if not isinstance(joint_map, dict) or not joint_map:
            return skill_error("Invalid joint_map", "joint_map must be a non-empty object")
        explicit_map = dict(joint_map)
    elif source_convention and target_convention:
        for label, value in (("source_convention", source_convention), ("target_convention", target_convention)):
            if value not in CONVENTIONS:
                return skill_error(
                    "Unknown naming convention",
                    "{} must be one of {}".format(label, ", ".join(CONVENTIONS)),
                    label=label,
                    value=value,
                )
        explicit_map = _biped_map(source_convention, target_convention)["pairs"]

    names = clip_names or ["clip_{:02d}".format(i + 1) for i in range(len(source_skeletons))]
    if len(names) != len(source_skeletons):
        return skill_error(
            "Clip count mismatch",
            "clip_names must contain one name per source skeleton",
        )

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = []  # Tracks nodes for best-effort cleanup on capability failure.
    try:
        container = get_node(hou, geo_path)
        target = get_node(hou, target_skeleton)
        sources = [get_node(hou, path) for path in source_skeletons]

        # F2: explicit/cross-convention mapping is only real when the source
        # skeletons carry the mapping attribute. Verify before building; error
        # (rather than report validated) when it is missing.
        if explicit_map:
            missing = [source.path() for source in sources if not _has_point_attrib(source, mapping_attribute)]
            if missing:
                return skill_error(
                    "Mapping attribute missing on source skeletons",
                    "mapping_attribute_missing",
                    mapping_attribute=mapping_attribute,
                    missing_sources=missing,
                    next_tools=["biped_joint_map", "configure_biped_retarget"],
                    hint="Author the mapping_attribute point values from joint_map before retargeting.",
                )

        clip_nodes = []
        solve_nodes = []

        for index, source in enumerate(sources, start=1):
            suffix = "{:02d}".format(index)
            match = _create(container, "kinefx::rigmatchpose", "{}_match_{}".format(node_prefix, suffix))
            match.setInput(0, target)
            match.setInput(1, source)
            _set_if_present(match, "bboxmatch", 1)

            mapping = _create(container, "kinefx::mappoints", "{}_map_{}".format(node_prefix, suffix))
            mapping.setInput(0, match, 0)
            mapping.setInput(1, match, 1)
            _set_if_present(mapping, "mappingattrib", mapping_attribute)
            _set_if_present(mapping, "referenceattrib", "name")
            # E1: explicit cross-convention mapping uses attribute mode (0),
            # otherwise keep the original auto-by-name behavior (1).
            _set_if_present(mapping, "automapinline", 0 if explicit_map else 1)
            if explicit_map:
                _set_if_present(mapping, "mapusing", 1)

            solve = _create(container, "kinefx::fullbodyik", "{}_solve_{}".format(node_prefix, suffix))
            solve.setInput(0, mapping, 0)
            solve.setInput(1, mapping, 1)
            _set_if_present(solve, "mapusing", 1)
            _set_if_present(solve, "mappingattribname", mapping_attribute)
            _set_if_present(solve, "attribtomatch", "name")
            _set_if_present(solve, "computelocaltransform", 1)

            clip = _create(container, "kinefx::motionclip", "{}_clip_{}".format(node_prefix, suffix))
            clip.setInput(0, solve)
            _set_if_present(clip, "useframerange", 1)
            _set_if_present(clip, "framerange1", start_frame)
            _set_if_present(clip, "framerange2", end_frame)
            clip_nodes.append(clip)
            solve_nodes.append(solve)
            created.extend((match, mapping, solve, clip))

        sequence = _create(container, "kinefx::motionclipsequence::2.0", "{}_sequence".format(node_prefix))
        sequence.setInput(0, clip_nodes[0])
        sequence.setInput(1, clip_nodes[1])
        blend = _create(container, "kinefx::motionclipblend::2.0", "{}_blend".format(node_prefix))
        blend.setInput(0, clip_nodes[0])
        blend.setInput(1, clip_nodes[1])
        _set_if_present(blend, "effect", 0.5)
        evaluate = _create(container, "kinefx::motionclipevaluate", "{}_evaluate".format(node_prefix))
        evaluate.setInput(0, blend)
        output = evaluate
        created.extend((sequence, blend, evaluate))

        if add_secondary_motion:
            secondary = _create(container, "kinefx::secondarymotion", "{}_secondary".format(node_prefix))
            secondary.setInput(0, evaluate)
            output = secondary
            created.append(secondary)

        pack = _create(container, "apex::packcharacter", "{}_apex_character".format(node_prefix))
        pack.setInput(2, target)
        pack.setInput(3, solve_nodes[0])
        _set_if_present(pack, "isscene", 1)
        _set_if_present(pack, "charname", character_name)
        _set_if_present(pack, "skelpath", "Base.skel")
        _set_if_present(pack, "rigpath", "Base.rig")
        _set_if_present(pack, "addbaserig", 1)

        scene = pack
        for index, (solve, clip_name) in enumerate(zip(solve_nodes, names), start=1):
            add_clip = _create(
                container, "apex::animationfromskeleton", "{}_apex_clip_{:02d}".format(node_prefix, index)
            )
            add_clip.setInput(0, scene)
            add_clip.setInput(1, solve)
            _set_if_present(add_clip, "rigpath", "/{}.char/Base.rig".format(character_name))
            _set_if_present(add_clip, "skeletonpath", "/{}.char/Base.skel".format(character_name))
            _set_if_present(add_clip, "mapusing", 1)
            _set_if_present(add_clip, "clipname", clip_name)
            _set_if_present(add_clip, "framerangemode", 1)
            _set_if_present(add_clip, "framerange1", start_frame)
            _set_if_present(add_clip, "framerange2", end_frame)
            scene = add_clip
            created.append(add_clip)

        mixer = _create(container, "kinefx::motionmixer", "{}_motion_mixer".format(node_prefix))
        mixer.setInput(0, scene)
        _set_if_present(mixer, "mixerstart", start_frame)
        _set_if_present(mixer, "mixerend", end_frame)
        fetch = _create(container, "kinefx::motionmixerfetch", "{}_motion_mixer_fetch".format(node_prefix))
        _set_if_present(fetch, "mixer", mixer.path())
        created.extend((pack, mixer, fetch))

        # Best-effort cook validation: a raised hou.OperationFailed is recorded
        # as a cook_failure (validated=False), never an uncaught exception that
        # turns the whole tool into success=False. Same discipline as the other
        # scene tools (QA blocking 1/2).
        failures = guarded_cook_failures(created)
        container.layoutChildren()

        return skill_success(
            "Built Houdini 22 retarget and Motion Mixer workflow",
            geo_path=container.path(),
            target_skeleton=target.path(),
            source_skeletons=[node.path() for node in sources],
            clip_names=names,
            clip_nodes=[node.path() for node in clip_nodes],
            mapping_mode="explicit" if explicit_map else "auto_by_name",
            mapping_attribute=mapping_attribute,
            mapping_attribute_verified=bool(explicit_map),
            joint_map=explicit_map or {},
            mapped_joint_count=len(explicit_map) if explicit_map else 0,
            sop_output=output.path(),
            apex_scene=scene.path(),
            motion_mixer=mixer.path(),
            motion_mixer_fetch=fetch.path(),
            created_nodes=[node.path() for node in created],
            cook_failures=failures,
            validated=not failures,
        )
    except RequiresHoudini22 as exc:
        # Stage 6 (Motion Mixer / APEX) needs Houdini 22-only node types. On
        # 20.5/21 those createNode calls fail with "Invalid node type name";
        # degrade to a structured capability error rather than an uncaught
        # hou.OperationFailed. Best-effort cleanup of the partial network so we
        # do not leave half-built nodes on the older host.
        created_paths = [node.path() for node in created]
        for node in created:
            try:
                node.destroy()
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                pass
        try:
            host_version = hou.applicationVersionString()
        except Exception:  # noqa: BLE001
            host_version = "unknown"
        return skill_error(
            "Motion Mixer workflow requires Houdini 22",
            "capability_unavailable",
            requires_houdini_22=True,
            missing_node_type=exc.node_type,
            host_version=host_version,
            created_nodes_before_failure=created_paths,
            hint=(
                "Stage 6 (Motion Mixer / full body IK) depends on Houdini 22-only "
                "KineFX/APEX node types. Use licensed Houdini 22 for the full "
                "workflow, or the single-source configure_biped_retarget path on "
                "older hosts."
            ),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to build retarget Motion Mixer workflow")


@skill_entry
def main(**kwargs) -> dict:
    return build_retarget_motion_mixer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
