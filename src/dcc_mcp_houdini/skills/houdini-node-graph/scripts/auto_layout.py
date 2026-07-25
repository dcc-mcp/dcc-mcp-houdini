"""Auto-layout a Houdini parent network with user-layout preservation.

Two strategies:
- ``houdini_default`` — use Houdini's built-in layoutChildren(),
  then restore user-touched node positions.
- ``tree_left_to_right`` — topological tree layout (sinks on the right).

Pass ``preserve_user_layout=true`` (default) to skip nodes whose
positions differ from the default Houdini arrangement (user-touched).
Pass ``dry_run=true`` to preview without mutating.
"""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def auto_layout(
    parent_path: str,
    strategy: str = "houdini_default",
    preserve_user_layout: bool = True,
    spacing_x: float = 200.0,
    spacing_y: float = 100.0,
    dry_run: bool = False,
) -> dict:
    """Auto-arrange nodes under *parent_path*."""
    try:
        __import__("hou")
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._node_graph_inspection import auto_layout as _auto_layout
    except ImportError as exc:
        return skill_error("Layout module unavailable", str(exc))

    if strategy not in ("houdini_default", "tree_left_to_right"):
        return skill_error(
            "Unknown layout strategy",
            "strategy must be 'houdini_default' or 'tree_left_to_right'",
        )

    try:
        result = _auto_layout(
            parent_path=parent_path,
            strategy=strategy,
            preserve_user_layout=preserve_user_layout,
            spacing_x=spacing_x,
            spacing_y=spacing_y,
            dry_run=dry_run,
        )
    except ValueError as exc:
        return skill_error("Invalid network path", str(exc))
    except RuntimeError as exc:
        return skill_error("Houdini runtime error", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to auto-layout Houdini network")

    return skill_success(
        "Auto-layout completed" if not dry_run else "Layout plan computed (dry run)",
        parent_path=result.parent_path,
        moved_count=result.moved_count,
        preserved_count=result.preserved_count,
        moved_paths=result.moved_paths,
        preserved_paths=result.preserved_paths,
        strategy=result.strategy,
        dry_run=dry_run,
    )


@skill_entry
def main(**kwargs) -> dict:
    return auto_layout(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
