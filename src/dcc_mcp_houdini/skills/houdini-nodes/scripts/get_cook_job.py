"""Read a durable isolated node-cook job."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini import _cook_jobs


@skill_entry
def main(job_id: str) -> dict:
    try:
        return skill_success("Read isolated Houdini node-cook job", **_cook_jobs.get_cook_job(job_id))
    except Exception as exc:
        return skill_exception(exc, message="Failed to read isolated Houdini node-cook job")
