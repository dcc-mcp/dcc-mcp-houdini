"""Get render statistics from a ROP node, Solaris product, or current session."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import eval_first_parm, get_node, node_summary  # noqa: E402


def get_render_stats(
    rop_path: Optional[str] = None,
) -> dict:
    """Read render statistics: samples, resolution, engine, memory, etc."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        stats: dict = {}
        info_sources: list = []

        if rop_path:
            node = get_node(hou, rop_path)
            info_sources.append(node.path())

            # Resolution
            res_x = eval_first_parm(node, ("res_overridex", "resx", "vm_resx"))
            res_y = eval_first_parm(node, ("res_overridey", "resy", "vm_resy"))
            if res_x and res_y:
                stats["resolution"] = [int(res_x), int(res_y)]

            # Samples
            pixel_samples = eval_first_parm(node, ("vm_samples", "pixelsamples"))
            if pixel_samples:
                stats["pixel_samples"] = (
                    int(pixel_samples) if isinstance(pixel_samples, (int, float)) else pixel_samples
                )

            # Renderer
            renderer = eval_first_parm(node, ("renderer", "vm_renderer", "vm_engine"))
            if renderer:
                stats["renderer"] = str(renderer)

            # Output
            output = eval_first_parm(
                node,
                (
                    "picture",
                    "vm_picture",
                    "lopoutput",
                    "sopoutput",
                    "filename",
                    "outputimage",
                ),
            )
            if output:
                stats["output"] = str(output)

            # Frame range
            f1 = eval_first_parm(node, ("f1",))
            f2 = eval_first_parm(node, ("f2",))
            if f1 is not None and f2 is not None:
                stats["frame_range"] = [float(f1), float(f2)]

            stats["node"] = node_summary(node)
        else:
            # Session-wide stats
            stats["frame"] = hou.frame()
            stats["fps"] = hou.fps()
            stats["frame_range"] = [hou.playbar.playbackRange()[0], hou.playbar.playbackRange()[1]]
            info_sources.append("session")

        return skill_success(
            "Retrieved render stats",
            stats=stats,
            sources=info_sources,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to get render stats")


@skill_entry
def main(**kwargs) -> dict:
    return get_render_stats(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
