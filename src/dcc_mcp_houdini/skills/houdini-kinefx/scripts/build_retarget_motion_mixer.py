"""Build a Houdini 22 KineFX retarget and APEX Motion Mixer network."""

from __future__ import annotations

from typing import Any

from _kinefx_common import get_node
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _set_if_present(node: Any, name: str, value: Any) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def _create(container: Any, type_name: str, name: str) -> Any:
    node = container.createNode(type_name, node_name=name)
    node.setComment("DCC-MCP typed Houdini 22 animation workflow")
    return node


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
) -> dict:
    """Create and cook a retarget, MotionClip, APEX, and Motion Mixer chain.

    ``target_skeleton`` and every item in ``source_skeletons`` are existing SOP
    paths. Source skeletons should be time-dependent KineFX skeleton geometry.
    At least two sources are required so the generated Motion Mixer has clips to
    combine.
    """
    if len(source_skeletons) < 2:
        return skill_error(
            "At least two source skeletons are required",
            "source_skeletons must contain two or more SOP paths",
        )
    if end_frame < start_frame:
        return skill_error("Invalid frame range", "end_frame must be >= start_frame")

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

    try:
        container = get_node(hou, geo_path)
        target = get_node(hou, target_skeleton)
        sources = [get_node(hou, path) for path in source_skeletons]
        clip_nodes = []
        solve_nodes = []
        created = []

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
            _set_if_present(mapping, "automapinline", 1)

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
            add_clip = _create(container, "apex::animationfromskeleton", "{}_apex_clip_{:02d}".format(node_prefix, index))
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

        failures = []
        for node in created:
            node.cook(force=True)
            errors = list(node.errors())
            warnings = list(node.warnings())
            if errors or warnings:
                failures.append({"path": node.path(), "errors": errors, "warnings": warnings})
        container.layoutChildren()

        return skill_success(
            "Built Houdini 22 retarget and Motion Mixer workflow",
            geo_path=container.path(),
            target_skeleton=target.path(),
            source_skeletons=[node.path() for node in sources],
            clip_names=names,
            clip_nodes=[node.path() for node in clip_nodes],
            sop_output=output.path(),
            apex_scene=scene.path(),
            motion_mixer=mixer.path(),
            motion_mixer_fetch=fetch.path(),
            created_nodes=[node.path() for node in created],
            cook_failures=failures,
            validated=not failures,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to build retarget Motion Mixer workflow")


@skill_entry
def main(**kwargs) -> dict:
    return build_retarget_motion_mixer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
