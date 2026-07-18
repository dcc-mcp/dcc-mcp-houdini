"""Read an isolated background render job without touching Houdini state."""

from __future__ import annotations

from _background_render import read_render_job  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def get_render_job(job_id: str, include_details: bool = False) -> dict:
    try:
        return skill_success(
            "Read background ROP job",
            **read_render_job(job_id, include_details=include_details),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read background ROP job")


@skill_entry
def main(**kwargs) -> dict:
    return get_render_job(**kwargs)
