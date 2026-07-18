"""Export CHOP channel data to object parameter keyframes."""

from __future__ import annotations

from typing import List, Optional

from _chops_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def export_to_keyframes(
    node_path: str,
    target_path: str,
    parm_names: List[str],
    frame_range: Optional[List[float]] = None,
    resample_rate: Optional[float] = None,
) -> dict:
    """Bake CHOP channel data to keyframes on *target_path* parameters.

    Evaluates the CHOP node's channels at every frame in *frame_range* and
    writes constant keyframes on the matching *parm_names* of *target_path*.

    When *frame_range* is omitted, the CHOP's own time range is used.
    *resample_rate* controls the sample interval (default: 1.0 frame).

    Args:
        node_path: Path to the CHOP node whose channels are read.
        target_path: Object node path to write keyframes to (e.g. ``/obj/geo1``).
        parm_names: List of parameter names on *target_path* to drive.
        frame_range: Optional ``[start, end]`` override for the bake range.
        resample_rate: Sampling step between frames (default 1.0).
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        chop_node = get_node(hou, node_path)
        target_node = get_node(hou, target_path)

        # Determine frame range.
        if frame_range and len(frame_range) >= 2:
            start, end = float(frame_range[0]), float(frame_range[1])
        else:
            try:
                tr = chop_node.timeRange()
                start, end = float(tr[0]), float(tr[1])
            except Exception:  # noqa: BLE001
                start, end = float(hou.frame()), float(hou.frame() + 100)

        step = float(resample_rate) if resample_rate else 1.0

        # Collect channel data per frame.
        exported: dict[str, int] = {}
        current_frame = hou.frame()
        try:
            for frame in _frame_range(start, end, step):
                hou.setFrame(frame)
                # Evaluate CHOP channels.
                try:
                    values = [chop_node.evalAtFrame(frame, i) for i in range(len(parm_names))]
                except Exception:  # noqa: BLE001
                    # Try named evaluation.
                    values = []
                    for pn in parm_names:
                        try:
                            values.append(chop_node.evalAtChannel(frame, pn))
                        except Exception:  # noqa: BLE001
                            values.append(0.0)

                for i, parm_name in enumerate(parm_names):
                    if i >= len(values):
                        break
                    parm = target_node.parm(parm_name)
                    if parm is None:
                        continue
                    kf = hou.Keyframe()
                    kf.setFrame(float(frame))
                    kf.setValue(float(values[i]))
                    parm.setKeyframe(kf)
                    exported[parm_name] = exported.get(parm_name, 0) + 1
        finally:
            hou.setFrame(current_frame)

        return skill_success(
            "Exported CHOP channels to keyframes",
            chop_path=node_path,
            target_path=target_node.path(),
            frame_range=[start, end],
            step=step,
            exported_parameters=exported,
            total_keyframes=sum(exported.values()),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export CHOP to keyframes")


def _frame_range(start: float, end: float, step: float):
    """Generate frame numbers from *start* to *end* inclusive with *step*."""
    f = start
    while f <= end + 1e-9:
        yield f
        f += step


@skill_entry
def main(**kwargs) -> dict:
    return export_to_keyframes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
