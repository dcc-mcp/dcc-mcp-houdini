"""Cancel an isolated background ROP job owned by this adapter process."""

from __future__ import annotations

from _background_render import cancel_render_job as _cancel_render_job  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def cancel_render_job(job_id: str) -> dict:
    try:
        result = _cancel_render_job(job_id)
        return skill_success("Resolved background ROP job cancellation", **result)
    except Exception as exc:
        return skill_exception(exc, message="Failed to cancel background ROP job")


@skill_entry
def main(**kwargs) -> dict:
    return cancel_render_job(**kwargs)
