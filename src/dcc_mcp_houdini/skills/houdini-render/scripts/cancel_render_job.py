"""Cancel an isolated background ROP job or a foreground chunked render."""

from __future__ import annotations

from _background_render import cancel_render_job as _cancel_background_job  # noqa: E402
from _chunked_utils import cancel_foreground_job  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def cancel_render_job(job_id: str) -> dict:
    try:
        # Try foreground chunked job first (prefixed "rop-fg-")
        if job_id.startswith("rop-fg-"):
            result = cancel_foreground_job(job_id)
            if result is None:
                return skill_success(
                    "Foreground job not found",
                    job_id=job_id,
                    state="unknown",
                )
            # Avoid passing 'message' key from ChunkedProgress that would
            # collide with skill_success's own 'message' parameter.
            safe_result = {k: v for k, v in result.items() if k != "message"}
            return skill_success(
                "Cancelled foreground ROP render",
                **safe_result,
            )
        # Fall through to background (subprocess) jobs
        result = _cancel_background_job(job_id)
        return skill_success("Resolved background ROP job cancellation", **result)
    except Exception as exc:
        return skill_exception(exc, message="Failed to cancel ROP job")


@skill_entry
def main(**kwargs) -> dict:
    return cancel_render_job(**kwargs)
