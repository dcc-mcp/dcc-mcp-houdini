"""Cancel one adapter-owned isolated Husk render job."""

from __future__ import annotations

from _husk_jobs import cancel_husk_job as _cancel_husk_job  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def cancel_husk_job(job_id: str) -> dict:
    try:
        return skill_success("Husk render cancellation status", **_cancel_husk_job(job_id))
    except Exception as exc:
        return skill_exception(exc, message="Failed to cancel Husk render job")


@skill_entry
def main(**kwargs) -> dict:
    return cancel_husk_job(**kwargs)
