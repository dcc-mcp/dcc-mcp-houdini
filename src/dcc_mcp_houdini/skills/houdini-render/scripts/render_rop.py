"""Render a ROP node and report written files, elapsed time, and warnings."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _background_render import launch_background_render  # noqa: E402
from _render_common import eval_first_parm, expanded_outputs, get_node, node_summary, render_node  # noqa: E402

_OUTPUT_PARMS = ("outputimage", "picture", "vm_picture", "sopoutput", "filename", "lopoutput")


def render_rop(
    rop_path: str,
    frame_range: Optional[List[float]] = None,
    background: Optional[bool] = None,
) -> dict:
    """Render the ROP at *rop_path*, returning written files and elapsed time."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rop = get_node(hou, rop_path)
        is_solaris = rop.type().name().split("::", 1)[0] == "usdrender_rop"
        if (is_solaris and rop.parm("execute") is None) or (
            not is_solaris and not callable(getattr(rop, "render", None))
        ):
            return skill_error(
                "Not a render node",
                "Node has no supported render action; expected a ROP/output driver",
                node_path=rop.path(),
            )
        output_pattern = eval_first_parm(rop, _OUTPUT_PARMS, preserve_string=True)
        use_background = bool(hou.isUIAvailable()) if background is None else background
        if use_background:
            job = launch_background_render(hou, rop.path(), frame_range, output_pattern)
            return skill_success(
                "Started background ROP render",
                rop=node_summary(rop),
                background=True,
                **job,
            )
        warnings: List[str] = []
        start = time.time()
        rendered = True
        try:
            applied_range, execution_mode = render_node(rop, frame_range)
        except Exception as render_exc:  # noqa: BLE001
            rendered = False
            applied_range = None
            execution_mode = None
            warnings.append("Render failed: {}".format(render_exc))
        elapsed = round(time.time() - start, 3)
        if hasattr(rop, "errors"):
            warnings.extend(list(rop.errors()))
        written = expanded_outputs(output_pattern)
        return skill_success(
            "Rendered ROP",
            rop=node_summary(rop),
            rendered=rendered,
            execution_mode=execution_mode,
            elapsed_secs=elapsed,
            frame_range=applied_range,
            output_pattern=output_pattern,
            written_files=written,
            skipped=[] if written or not output_pattern else [output_pattern],
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to render ROP")


@skill_entry
def main(**kwargs) -> dict:
    return render_rop(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
