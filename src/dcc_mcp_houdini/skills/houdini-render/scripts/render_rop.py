"""Render a ROP node and report written files, elapsed time, and diagnostics."""

from __future__ import annotations

import glob
import os
import time
from typing import List, Optional

from _background_render import launch_background_render  # noqa: E402
from _render_common import (  # noqa: E402
    PRIMARY_OUTPUT_PARMS,
    build_per_frame_steps,
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
        applied_range = None
        execution_mode = None

        # Decide whether to use chunked runner for foreground multi-frame renders.
        # Solaris (usdrender_rop) cannot render per-frame, so it stays single-call.
        has_multi_frame = frame_range is not None and len(frame_range) >= 2
        if has_multi_frame:
            f_start = float(frame_range[0])
            f_end = float(frame_range[1])
            multi_frame = abs(f_end - f_start) > 1e-9
        else:
            multi_frame = False

        use_chunked = has_multi_frame and multi_frame and not is_solaris

        if use_chunked:
            from _chunked_utils import _register_foreground_job, pump_runner_via_event_loop

            from dcc_mcp_core.cancellation import CancelToken
            from dcc_mcp_core.chunked_runner import ChunkedRunner

            steps = build_per_frame_steps(rop, frame_range)
            token = CancelToken()
            runner = ChunkedRunner(steps, total=len(steps), cancel_token=token)
            job_id = _register_foreground_job(
                runner, token, rop.path(), list(frame_range), len(steps)
            )

            # Block until terminal by pumping the runner through the event loop
            pump_runner_via_event_loop(runner)

            outcome = runner.outcome
            if outcome is None:
                rendered = False
                errors.append("Chunked runner finished without a terminal outcome")
            elif outcome.status == "cancelled":
                rendered = True
                errors.append(
                    "Render cancelled after {} of {} frames".format(
                        outcome.progress.completed, outcome.progress.total
                    )
                )
            elif outcome.status == "failed":
                rendered = False
                errors.append("Render failed: {}".format(outcome.error))
            else:
                rendered = True

            applied_range = [float(frame_range[0]), float(frame_range[1])]
            execution_mode = "chunked"
            elapsed = round(time.time() - start, 3)

            # Collect partial/completed outputs
            if outcome is not None:
                completed_frames = outcome.progress.completed
            else:
                completed_frames = 0

            rop_errors = getattr(rop, "errors", None)
            if callable(rop_errors):
                errors.extend(str(error) for error in rop_errors())
            rop_warnings = getattr(rop, "warnings", None)
            if callable(rop_warnings):
                warnings.extend(str(warning) for warning in rop_warnings())

            written = expanded_outputs(output_pattern)
            total_frames = len(steps)
            skipped = list(
                range(int(frame_range[0]) + completed_frames, int(frame_range[1]) + 1)
            ) if completed_frames < total_frames else []

            return skill_success(
                "Rendered ROP (chunked)" if rendered else "ROP render cancelled/failed",
                rop=node_summary(rop),
                rendered=rendered,
                execution_mode=execution_mode,
                elapsed_secs=elapsed,
                frame_range=applied_range,
                output_pattern=output_pattern,
                written_files=written,
                completed_frames=completed_frames,
                total_frames=total_frames,
                skipped=skipped,
                errors=errors,
                warnings=warnings,
            )
        else:
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
