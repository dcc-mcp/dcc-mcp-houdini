"""Publish externally validated staged render outputs without clobbering finals."""

from __future__ import annotations

from _background_render import finalize_render_outputs as _finalize_render_outputs  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def finalize_render_outputs(job_id: str, validator_receipts: list) -> dict:
    try:
        return skill_success(
            "Finalized validated render outputs",
            **_finalize_render_outputs(job_id, validator_receipts),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to finalize render outputs")


@skill_entry
def main(**kwargs) -> dict:
    return finalize_render_outputs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
