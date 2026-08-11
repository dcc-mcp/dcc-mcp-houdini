"""Render a USD file with husk command-line renderer (Karma or other Hydra delegate)."""

from __future__ import annotations

import os
import re
from typing import List, Optional

from _husk_common import (  # noqa: E402
    build_husk_command,
    find_husk,
    husk_subprocess_environment,
    resolve_husk_renderer,
)
from _husk_jobs import launch_husk_job  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_FRAME_TOKEN = re.compile(r"\$F(\d*)")


def _expand_frame_token(output_path: str, frame: float) -> str:
    """Expand Houdini's $F/$F4-style token for artifact verification."""
    if not float(frame).is_integer():
        return output_path
    frame_number = int(frame)

    def replace(match: re.Match[str]) -> str:
        width = int(match.group(1) or 0)
        return str(frame_number).zfill(width) if width else str(frame_number)

    return _FRAME_TOKEN.sub(replace, output_path)


def _expected_output_paths(
    output_path: str,
    frame: Optional[int],
    frame_range: Optional[List[float]],
) -> list[str]:
    if frame is not None:
        return [_expand_frame_token(output_path, frame)]
    if frame_range:
        start, end = float(frame_range[0]), float(frame_range[1])
        increment = float(frame_range[2]) if len(frame_range) > 2 else 1.0
        if increment <= 0:
            return []
        frame_values = []
        current = start
        while current <= end + 1.0e-9:
            frame_values.append(current)
            current += increment
        return [_expand_frame_token(output_path, value) for value in frame_values]
    return [output_path]


def _output_glob(output_path: str, frame: Optional[int], frame_range: Optional[List[float]]) -> str:
    if _FRAME_TOKEN.search(output_path):
        return _FRAME_TOKEN.sub("*", output_path)
    if frame is not None or frame_range:
        base, extension = os.path.splitext(output_path)
        return "{}.*{}".format(base, extension)
    return output_path


def render_with_husk(
    usd_file: str,
    output_path: str,
    renderer: str = "karma",
    frame: Optional[int] = None,
    frame_range: Optional[List[float]] = None,
    resolution: Optional[List[int]] = None,
    husk_args: Optional[List[str]] = None,
    use_hython_fallback: bool = False,
) -> dict:
    """Launch an isolated Husk render and return a durable job identifier."""

    if use_hython_fallback:
        return skill_error(
            "Blocking hython fallback is disabled",
            "use_hython_fallback cannot preserve Houdini UI responsiveness. Export a USD snapshot, then launch native Husk.",
            prompt="Call create_snapshot first, then call render_with_husk with use_hython_fallback=false.",
        )

    # Native husk CLI path
    husk_path = find_husk()
    if not husk_path:
        return skill_error(
            "husk not found",
            "husk executable not found. Set HFS or ensure Houdini is installed.",
        )

    try:
        output_directory = os.path.dirname(os.path.abspath(output_path))
        if output_directory:
            os.makedirs(output_directory, exist_ok=True)

        resolved_renderer = resolve_husk_renderer(renderer)
        cmd = build_husk_command(
            usd_file=usd_file,
            output_path=output_path,
            frame=frame,
            frame_range=frame_range,
            renderer=renderer,
            resolution=resolution,
            extra_args=husk_args,
        )
        # Replace 'husk' with actual path
        cmd[0] = husk_path

        expected_outputs = _expected_output_paths(output_path, frame, frame_range)
        job = launch_husk_job(
            command=cmd,
            output_path=output_path,
            expected_outputs=expected_outputs,
            output_glob=_output_glob(output_path, frame, frame_range),
            environment=husk_subprocess_environment(),
            timeout_secs=3600,
        )
        context = dict(job)
        context.update(
            {
                "background": True,
                "usd_file": usd_file,
                "output_path": output_path,
                "expected_outputs": expected_outputs,
                "renderer": resolved_renderer,
                "requested_renderer": renderer,
                "command": " ".join(cmd),
            }
        )
        return skill_success(
            "Started isolated Husk render",
            prompt="Poll get_husk_job with this job_id; call cancel_husk_job to stop the owned worker tree.",
            **context,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to launch isolated Husk render")


@skill_entry
def main(**kwargs) -> dict:
    return render_with_husk(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
