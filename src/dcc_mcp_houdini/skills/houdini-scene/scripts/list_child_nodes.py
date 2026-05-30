"""List child nodes below a Houdini network path."""

from __future__ import annotations

from typing import Any, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _type_name(node: Any) -> str:
    type_obj = node.type()
    return type_obj.name() if hasattr(type_obj, "name") else str(type_obj)


def _optional_bool(node: Any, method_name: str) -> bool:
    method = getattr(node, method_name, None)
    if not callable(method):
        return False
    try:
        return bool(method())
    except Exception:
        return False


def _node_summary(node: Any, depth: int) -> dict:
    return {
        "path": node.path(),
        "name": node.name(),
        "type": _type_name(node),
        "depth": depth,
        "hidden": _optional_bool(node, "isHidden"),
    }


def list_child_nodes(
    parent_path: str = "/obj",
    type_filter: Optional[str] = None,
    recursive: bool = False,
    max_depth: int = 1,
    include_hidden: bool = False,
) -> dict:
    """List child nodes below *parent_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = hou.node(parent_path)
        if parent is None:
            return skill_error("Houdini node not found", parent_path)
        if max_depth < 0:
            return skill_error("Invalid max_depth", "max_depth must be >= 0")

        nodes: List[dict] = []
        lowered_filter = type_filter.lower() if type_filter else None

        def visit(container: Any, depth: int) -> None:
            for child in container.children():
                hidden = _optional_bool(child, "isHidden")
                type_name = _type_name(child)
                if include_hidden or not hidden:
                    if lowered_filter is None or lowered_filter in type_name.lower():
                        nodes.append(_node_summary(child, depth))
                if recursive and depth < max_depth:
                    visit(child, depth + 1)

        visit(parent, 0)
        return skill_success(
            "Listed Houdini child nodes",
            parent_path=parent.path(),
            nodes=nodes,
            count=len(nodes),
            type_filter=type_filter,
            recursive=recursive,
            max_depth=max_depth,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list Houdini child nodes")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_child_nodes`."""
    return list_child_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
