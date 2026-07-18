"""Introspect HOM objects, signatures, node categories, and node types."""

from __future__ import annotations

import inspect
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _resolve_attr(hou, dotted: str):
    obj = hou
    for part in dotted.split("."):
        if part == "hou":
            continue
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def introspect_hom(
    target: Optional[str] = None,
    category: Optional[str] = None,
    name_filter: Optional[str] = None,
    limit: int = 200,
) -> dict:
    """Introspect HOM for agent planning.

    Provide ``target`` (e.g. ``hou.Node`` / ``hou.node``) to dump members and a
    callable signature, or ``category`` (e.g. ``Sop``/``Object``) to list node
    types in that category. With neither, list available node-type categories.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if target:
            obj = _resolve_attr(hou, target)
            if obj is None:
                return skill_error("Target not found", "No HOM attribute {!r}".format(target))
            members = [m for m in dir(obj) if not m.startswith("_")]
            signature = None
            doc = inspect.getdoc(obj)
            if callable(obj):
                try:
                    signature = str(inspect.signature(obj))
                except (TypeError, ValueError):
                    signature = None
            return skill_success(
                "Introspected HOM target",
                target=target,
                callable=callable(obj),
                signature=signature,
                doc=(doc.splitlines()[0] if doc else None),
                member_count=len(members),
                members=members[:limit],
            )

        categories = {}
        for getter in dir(hou):
            if not getter.endswith("NodeTypeCategory"):
                continue
            fn = getattr(hou, getter, None)
            if not callable(fn):
                continue
            try:
                cat = fn()
                categories[cat.name()] = getter
            except Exception:  # noqa: BLE001
                continue

        if not category:
            return skill_success(
                "Listed node categories",
                categories=sorted(categories.keys()),
            )

        getter_name = categories.get(category)
        if getter_name is None:
            return skill_error(
                "Unknown category",
                "No node-type category {!r}".format(category),
                available=sorted(categories.keys()),
            )
        cat = getattr(hou, getter_name)()
        type_names = sorted(cat.nodeTypes().keys())
        if name_filter:
            needle = name_filter.lower()
            type_names = [n for n in type_names if needle in n.lower()]
        return skill_success(
            "Listed node types",
            category=category,
            count=len(type_names),
            node_types=type_names[:limit],
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to introspect HOM")


@skill_entry
def main(**kwargs) -> dict:
    return introspect_hom(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
