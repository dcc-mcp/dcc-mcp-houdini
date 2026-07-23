"""Bake evaluated parameter values into per-frame keyframes over a range."""

from __future__ import annotations

from typing import List

from _anim_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini.api import safe_parm_eval

_MAX_FRAMES = 100000


def bake_channels(
    node_path: str,
    parm_names: List[str],
    frame_range: List[float],
    step: float = 1.0,
) -> dict:
    """Sample *parm_names* each frame in range and write constant keyframes.

    Samples are collected first, then applied, so setting a key never perturbs
    later samples. Bounded by a hard frame cap to avoid runaway bakes.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if not frame_range or len(frame_range) < 2:
        return skill_error("Invalid frame range", "frame_range must be [start, end]")
    start, end = float(frame_range[0]), float(frame_range[1])
    step = float(step) if step else 1.0
    if step <= 0:
        return skill_error("Invalid step", "step must be > 0")
    if (end - start) / step > _MAX_FRAMES:
        return skill_error(
            "Frame range too large",
            "Refusing to bake more than {} frames".format(_MAX_FRAMES),
            frame_range=[start, end],
            step=step,
        )

    try:
        node = get_node(hou, node_path)
        parms = {}
        missing = []
        for name in parm_names:
            parm = node.parm(name)
            if parm is None:
                missing.append(name)
            else:
                parms[name] = parm
        if not parms:
            return skill_error("No valid parameters", "None of parm_names exist", missing=missing)

        original_frame = hou.frame() if hasattr(hou, "frame") else start
        samples = {name: [] for name in parms}
        frame = start
        while frame <= end + 1e-6:
            hou.setFrame(frame)
            for name, parm in parms.items():
                samples[name].append((frame, safe_parm_eval(parm)))
            frame += step
        hou.setFrame(original_frame)

        baked = {}
        for name, parm in parms.items():
            for sample_frame, value in samples[name]:
                kf = hou.Keyframe()
                kf.setFrame(sample_frame)
                kf.setValue(float(value))
                parm.setKeyframe(kf)
            baked[name] = len(samples[name])
        return skill_success(
            "Baked channels",
            node_path=node.path(),
            frame_range=[start, end],
            step=step,
            baked=baked,
            missing=missing,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to bake channels")


@skill_entry
def main(**kwargs) -> dict:
    return bake_channels(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
