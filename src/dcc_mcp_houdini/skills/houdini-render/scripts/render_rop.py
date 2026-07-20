"""Render a ROP node and report written files, elapsed time, and diagnostics."""

from __future__ import annotations

import glob
import os
import time
from typing import List, Optional

from _background_render import launch_background_render  # noqa: E402
from _render_common import (  # noqa: E402
    PRIMARY_OUTPUT_PARMS,
    eval_first_parm,
    expanded_outputs,
    get_node,
    node_summary,
    render_node,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


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
    artifact_transaction: Optional[dict] = None,
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
        output_pattern = eval_first_parm(rop, PRIMARY_OUTPUT_PARMS, preserve_string=True)
        use_background = True if background is None else background
        if artifact_transaction is not None and not use_background:
            return skill_error(
                "Artifact transaction requires background rendering",
                "staged_no_clobber is available only for isolated ROP jobs",
            )
        if use_background:
            if artifact_transaction is None:
                job = launch_background_render(hou, rop.path(), frame_range, output_pattern)
            else:
                job = launch_background_render(
                    hou,
                    rop.path(),
                    frame_range,
                    output_pattern,
                    artifact_transaction=artifact_transaction,
                )
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
        try:
            applied_range, execution_mode = render_node(rop, frame_range)
        except Exception as render_exc:  # noqa: BLE001
            rendered = False
            applied_range = None
            execution_mode = None
            errors.append("Render failed: {}".format(render_exc))
        elapsed = round(time.time() - start, 3)
        rop_errors = getattr(rop, "errors", None)
        if callable(rop_errors):
            errors.extend(str(error) for error in rop_errors())
        rop_warnings = getattr(rop, "warnings", None)
        if callable(rop_warnings):
            warnings.extend(str(warning) for warning in rop_warnings())
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
