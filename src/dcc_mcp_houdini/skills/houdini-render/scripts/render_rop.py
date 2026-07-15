"""Render a ROP node and report written files, elapsed time, and diagnostics."""

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

from _background_render import launch_background_render  # noqa: E402
from _render_common import apply_frame_range, eval_first_parm, get_node, node_summary  # noqa: E402

_OUTPUT_PARMS = ("picture", "vm_picture", "lopoutput", "sopoutput", "filename", "outputimage")


def _expand_outputs(pattern: Optional[str]) -> list:
    if not pattern:
        return []
    if isinstance(pattern, (list, tuple)):
        pattern = pattern[0] if len(pattern) == 1 else None
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
        use_background = True if background is None else background
        if use_background:
            job = launch_background_render(hou, rop.path(), frame_range, output_pattern)
            return skill_success(
                "Started background ROP render",
                rop=node_summary(rop),
                background=True,
                **job,
            )
        errors: List[str] = []
        warnings: List[str] = []
        start = time.time()
        rendered = True
        render_kwargs = {}
        if frame_range:
            render_kwargs["frame_range"] = (
                float(frame_range[0]),
                float(frame_range[1]),
                float(frame_range[2]) if len(frame_range) > 2 else 1.0,
            )
        applied_range = apply_frame_range(rop, frame_range) if frame_range else None
        try:
            rop.render(verbose=False, **render_kwargs)
        except TypeError:
            rop.render(**render_kwargs)
        except Exception as render_exc:  # noqa: BLE001
            rendered = False
            applied_range = None
            errors.append("Render failed: {}".format(render_exc))
        elapsed = round(time.time() - start, 3)
        rop_errors = getattr(rop, "errors", None)
        if callable(rop_errors):
            errors.extend(str(error) for error in rop_errors())
        rop_warnings = getattr(rop, "warnings", None)
        if callable(rop_warnings):
            warnings.extend(str(warning) for warning in rop_warnings())
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
            errors=errors,
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
