"""Read back metadata from a Wrangle node — read-only, never cooks."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_vex_info(node_path: str) -> dict:
    """Return Wrangle metadata for *node_path* without cooking or mutating."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._vex_executor import get_wrangle_info
    except ImportError as exc:
        return skill_error("VEX module not available", str(exc))

    try:
        info = get_wrangle_info(hou, node_path)
        return skill_success("Read Wrangle info", **info.to_dict())
    except ValueError as exc:
        return skill_error("Node not found", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to read Wrangle info")


@skill_entry
def main(**kwargs) -> dict:
    return get_vex_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
