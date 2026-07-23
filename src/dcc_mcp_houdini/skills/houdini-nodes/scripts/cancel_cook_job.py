"""Cancel an owned isolated node-cook job."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini import _cook_jobs


@skill_entry
def main(job_id: str) -> dict:
    try:
        return skill_success("Processed node-cook cancellation", **_cook_jobs.cancel_cook_job(job_id))
    except Exception as exc:
        return skill_exception(exc, message="Failed to cancel isolated Houdini node-cook job")
