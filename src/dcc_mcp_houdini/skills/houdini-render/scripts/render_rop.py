"""Render a ROP node and report written files, elapsed time, and warnings."""

from __future__ import annotations

import glob
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import (  # noqa: E402
    apply_frame_range,
    eval_first_parm,
    get_node,
    node_summary,
)

_OUTPUT_PARMS = ("picture", "vm_picture", "lopoutput", "sopoutput", "filename", "outputimage")


def _expand_outputs(pattern: Optional[str]) -> list:
    if not pattern:
        return []
    globbed = pattern
    for token in ("$F4", "$F3", "$F2", "$F"):
        globbed = globbed.replace(token, "*")
    if "*" in globbed:
        return sorted(glob.glob(globbed))
    return [pattern] if os.path.isfile(pattern) else []


def render_rop(
    rop_path: str,
    frame_range: Optional[List[float]] = None,
) -> dict:
    """Render the ROP at *rop_path*, returning written files and elapsed time."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rop = get_node(hou, rop_path)
        if not hasattr(rop, "render"):
            return skill_error(
                "Not a render node",
                "Node has no render(); expected a ROP/output driver",
                node_path=rop.path(),
            )
        applied_range = apply_frame_range(rop, frame_range) if frame_range else None
        output_pattern = eval_first_parm(rop, _OUTPUT_PARMS)
        warnings: List[str] = []
        start = time.time()
        rendered = True
        try:
            rop.render(verbose=False)
        except TypeError:
            rop.render()
        except Exception as render_exc:  # noqa: BLE001
            rendered = False
            warnings.append("Render failed: {}".format(render_exc))
        elapsed = round(time.time() - start, 3)
        if hasattr(rop, "errors"):
            warnings.extend(list(rop.errors()))
        written = _expand_outputs(output_pattern)
        return skill_success(
            "Rendered ROP",
            rop=node_summary(rop),
            rendered=rendered,
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
