"""Inspect a Houdini node without changing the scene."""

from __future__ import annotations

from typing import Any, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _call_or_none(obj: Any, method_name: str) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _path_or_none(node: Any) -> Optional[str]:
    if node is None:
        return None
    path = _call_or_none(node, "path")
    return str(path) if path is not None else None


def _optional_bool(node: Any, method_name: str) -> Optional[bool]:
    value = _call_or_none(node, method_name)
    return bool(value) if value is not None else None


def _type_context(node: Any) -> dict:
    type_obj = node.type()
    category = _call_or_none(type_obj, "category")
    return {
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
        "category": category.name() if category is not None and hasattr(category, "name") else None,
    }


def _connection_paths(nodes: Any) -> List[Optional[str]]:
    if nodes is None:
        return []
    return [_path_or_none(node) for node in nodes]


def get_node_info(node_path: str, include_connections: bool = True) -> dict:
    """Return a JSON-safe summary for *node_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = hou.node(node_path)
        if node is None:
            return skill_error("Houdini node not found", node_path)

        children = list(node.children())
        context = {
            "path": node.path(),
            "name": node.name(),
            "parent_path": _path_or_none(_call_or_none(node, "parent")),
            "child_count": len(children),
            "children": [_path_or_none(child) for child in children],
            "flags": {
                "bypassed": _optional_bool(node, "isBypassed"),
                "display": _optional_bool(node, "isDisplayFlagSet"),
                "render": _optional_bool(node, "isRenderFlagSet"),
                "template": _optional_bool(node, "isTemplateFlagSet"),
                "current": _optional_bool(node, "isCurrent"),
                "selected": _optional_bool(node, "isSelected"),
                "hidden": _optional_bool(node, "isHidden"),
            },
        }
        context.update(_type_context(node))
        if include_connections:
            context["inputs"] = _connection_paths(_call_or_none(node, "inputs"))
            context["outputs"] = _connection_paths(_call_or_none(node, "outputs"))

        return skill_success("Inspected Houdini node", node=context)
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect Houdini node")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_node_info`."""
    return get_node_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
