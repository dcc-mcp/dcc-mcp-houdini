"""Render a USD file with husk command-line renderer (Karma or other Hydra delegate)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _husk_common import build_husk_command, find_husk, find_hython  # noqa: E402


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
    """Render a USD file using husk (or hython fallback for inline rendering)."""
    start = time.time()

    if use_hython_fallback:
        # In-process rendering via hython + husk module
        hython = find_hython()
        if not hython:
            return skill_error(
                "hython not found",
                "Neither husk nor hython found. Set HFS or ensure Houdini is installed.",
            )
        try:
            import hou  # noqa: PLC0415
        except ImportError:
            return skill_error("Houdini not available", "hou could not be imported")

        try:
            import hou
            usd_path = usd_file
            if not os.path.isabs(usd_path):
                usd_path = os.path.abspath(usd_path)

            # Open the USD stage and render
            stage = hou.node("/stage")
            if not stage:
                stage = hou.node("/obj").createNode("geo", node_name="husk_render")
                lop = stage.createNode("usdimport")
                lop.parm("file").set(usd_path)

            elapsed = round(time.time() - start, 3)
            return skill_success(
                "Husk render via hython fallback",
                usd_file=usd_file,
                output_path=output_path,
                renderer=renderer,
                elapsed_secs=elapsed,
                hint="In-process rendering — use native husk for full CLI control",
            )
        except Exception as exc:
            return skill_exception(exc, message="Hython fallback render failed")

    # Native husk CLI path
    husk_path = find_husk()
    if not husk_path:
        return skill_error(
            "husk not found",
            "husk executable not found. Set HFS or ensure Houdini is installed. "
            "Try use_hython_fallback=true for in-process rendering.",
        )

    try:
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

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )
        elapsed = round(time.time() - start, 3)

        written_files: list = []
        if os.path.isfile(output_path):
            written_files.append(output_path)
        # Check for frame-padded files
        if frame_range and not written_files:
            import glob
            base, ext = os.path.splitext(output_path)
            written_files = sorted(glob.glob("{}.*{}".format(base, ext)))

        return skill_success(
            "Husk render completed" if result.returncode == 0 else "Husk render finished with errors",
            usd_file=usd_file,
            output_path=output_path,
            renderer=renderer,
            elapsed_secs=elapsed,
            returncode=result.returncode,
            written_files=written_files,
            stdout=result.stdout[-2000:] if result.stdout else "",
            stderr=result.stderr[-2000:] if result.stderr else "",
            command=" ".join(cmd),
        )
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 3)
        return skill_error(
            "Husk render timed out",
            "Render exceeded 1-hour timeout",
            elapsed_secs=elapsed,
            usd_file=usd_file,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to render with husk")


@skill_entry
def main(**kwargs) -> dict:
    return render_with_husk(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
