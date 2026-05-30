"""List object-level nodes under /obj."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_obj_nodes(type_filter: Optional[str] = None) -> dict:
    """List nodes in /obj, optionally filtered by node type name."""
    try:
        import hou  # noqa: PLC0415

        obj = hou.node("/obj")
        if obj is None:
            return skill_error("Object context missing", "/obj not found")

        nodes = []
        for child in obj.children():
            type_name = child.type().name()
            if type_filter and type_filter.lower() not in type_name.lower():
                continue
            nodes.append(
                {
                    "path": child.path(),
                    "name": child.name(),
                    "type": type_name,
                }
            )

        return skill_success(
            "Listed object nodes",
            nodes=nodes,
            count=len(nodes),
            type_filter=type_filter,
        )
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list object nodes")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_obj_nodes`."""
    return list_obj_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
