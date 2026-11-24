"""Launch, poll, or cancel a chunked ROP render job."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry
from render_rop import render_rop_chunked


@skill_entry
def main(**kwargs) -> dict:
    return render_rop_chunked(**kwargs)
