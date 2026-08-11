"""Read one isolated Husk render job."""

from __future__ import annotations

from _husk_jobs import read_husk_job  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def get_husk_job(job_id: str) -> dict:
    try:
        return skill_success("Husk render job status", **read_husk_job(job_id))
    except Exception as exc:
        return skill_exception(exc, message="Failed to read Husk render job")


@skill_entry
def main(**kwargs) -> dict:
    return get_husk_job(**kwargs)
