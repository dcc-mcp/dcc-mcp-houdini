"""Cancel a chunked viewport flipbook job."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry
from flipbook import cancel_flipbook_job


@skill_entry
def main(**kwargs) -> dict:
    return cancel_flipbook_job(**kwargs)
