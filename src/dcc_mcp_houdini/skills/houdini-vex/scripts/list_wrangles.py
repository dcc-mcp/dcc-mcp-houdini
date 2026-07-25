"""List all Wrangle-type nodes under a parent path, recursively."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_wrangles(parent_path: str = "/obj") -> dict:
    """List all Wrangle nodes under *parent_path* (recursive)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._vex_executor import list_wrangles as _list
    except ImportError as exc:
        return skill_error("VEX module not available", str(exc))

    try:
        results = _list(hou, parent_path)
        return skill_success(
            f"Found {len(results)} Wrangle node(s)",
            count=len(results),
            wrangles=results,
        )
    except ValueError as exc:
        return skill_error("Invalid parent path", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to list Wrangles")


@skill_entry
def main(**kwargs) -> dict:
    return list_wrangles(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
