"""Query the current Houdini project root ($JOB) and hip file location."""

from __future__ import annotations

import os
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_project() -> dict:
    """Return ``$JOB``, ``$HIP``, the hip file path, and existence flags."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        job = hou.getenv("JOB") or os.environ.get("JOB")
        hip = hou.getenv("HIP") or os.environ.get("HIP")
        hip_file = None
        try:
            hip_file = hou.hipFile.path()
        except Exception:  # noqa: BLE001
            hip_file = None
        return skill_success(
            "Queried project",
            job=job,
            hip=hip,
            hip_file=hip_file,
            job_exists=bool(job and Path(job).is_dir()),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to query project")


@skill_entry
def main(**kwargs) -> dict:
    return get_project(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
