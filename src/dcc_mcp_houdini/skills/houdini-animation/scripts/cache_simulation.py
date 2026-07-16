"""Bake a simulation/cache by rendering a ROP and reporting output paths."""

from __future__ import annotations

import glob
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini._rop_jobs import launch_background_render

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _anim_common import get_node  # noqa: E402

_OUTPUT_PARMS = ("file", "sopoutput", "filename", "dopoutput", "picture", "outputimage")


def _set_frame_range(node, frame_range):
    if not frame_range or len(frame_range) < 2:
        return None
    start, end = float(frame_range[0]), float(frame_range[1])
    if node.parm("trange") is not None:
        node.parm("trange").set(1)
    tuple_parm = node.parmTuple("f")
    if tuple_parm is not None:
        step = float(frame_range[2]) if len(frame_range) > 2 else 1.0
        tuple_parm.set((start, end, step))
    return [start, end]


def _eval_output(node, preserve_string: bool = False) -> Optional[str]:
    for name in _OUTPUT_PARMS:
        parm = node.parm(name)
        if parm is not None:
            if preserve_string:
                try:
                    value = parm.unexpandedString()
                    if isinstance(value, str):
                        return value
                except Exception:  # noqa: BLE001
                    pass
            try:
                return parm.eval()
            except Exception:  # noqa: BLE001
                continue
    return None


def _expand(pattern: Optional[str]) -> list:
    if not pattern:
        return []
    globbed = pattern
    for token in ("$F4", "$F3", "$F2", "$F"):
        globbed = globbed.replace(token, "*")
    if "*" in globbed:
        return sorted(glob.glob(globbed))
    return [pattern] if os.path.isfile(pattern) else []


def cache_simulation(
    rop_path: str,
    frame_range: Optional[List[float]] = None,
    background: Optional[bool] = None,
) -> dict:
    """Render a cache/sim ROP (filecache/dop/geometry) and report outputs."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rop = get_node(hou, rop_path)
        if not hasattr(rop, "render"):
            return skill_error(
                "Not a cache/render node",
                "Node has no render(); expected a ROP/file cache node",
                node_path=rop.path(),
            )
        use_background = bool(hou.isUIAvailable()) if background is None else background
        output_pattern = _eval_output(rop, preserve_string=use_background)
        if use_background:
            job = launch_background_render(
                hou,
                rop.path(),
                frame_range,
                output_pattern,
                job_kind="cache",
            )
            return skill_success(
                "Started background simulation cache",
                node_path=rop.path(),
                background=True,
                **job,
            )
        applied_range = _set_frame_range(rop, frame_range)
        warnings: List[str] = []
        start = time.time()
        cached = True
        try:
            rop.render(verbose=False)
        except TypeError:
            rop.render()
        except Exception as render_exc:  # noqa: BLE001
            cached = False
            warnings.append("Cache render failed: {}".format(render_exc))
        elapsed = round(time.time() - start, 3)
        written = _expand(output_pattern)
        return skill_success(
            "Cached simulation",
            node_path=rop.path(),
            background=False,
            cached=cached,
            elapsed_secs=elapsed,
            frame_range=applied_range,
            output_pattern=output_pattern,
            written_files=written,
            skipped=[] if written or not output_pattern else [output_pattern],
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to cache simulation")


@skill_entry
def main(**kwargs) -> dict:
    return cache_simulation(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
