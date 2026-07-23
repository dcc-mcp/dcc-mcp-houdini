"""Launch a durable isolated node cook."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini import _cook_jobs


@skill_entry
def main(node_path: str, force: bool = False) -> dict:
    try:
        import hou

        job = _cook_jobs.launch_cook_job(hou, node_path, force)
        return skill_success(
            "Started isolated Houdini node cook",
            **job,
            recovery={
                "poll_tool": "houdini_nodes__get_cook_job",
                "cancel_tool": "houdini_nodes__cancel_cook_job",
                "survives_transport_disconnect": True,
            },
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to start isolated Houdini node cook")
