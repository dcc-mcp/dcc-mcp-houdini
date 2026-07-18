"""Import a geometry/scene file into a SOP network via a File SOP."""

from __future__ import annotations

from typing import Optional

from _io_common import (  # noqa: E402
    detect_format,
    get_node,
    node_summary,
    probe,
    set_first_parm,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def import_geometry(
    parent_path: str,
    file_path: str,
    node_name: Optional[str] = None,
    cook: bool = True,
) -> dict:
    """Create a File SOP under *parent_path* reading *file_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    info = probe(file_path)
    if not info["exists"]:
        return skill_error(
            "File not found",
            "No file at the given path",
            file_path=file_path,
        )
    if not info["is_supported_import"]:
        return skill_error(
            "Unsupported import format",
            "Detected format {!r} is not a supported File SOP import".format(info["format"]),
            file_path=file_path,
            format=info["format"],
        )
    try:
        parent = get_node(hou, parent_path)
        node = parent.createNode("file", node_name=node_name)
        used = set_first_parm(node, ("file", "filename"), file_path)
        if used is None:
            return skill_error(
                "Could not set file parameter",
                "File SOP has no recognised file parm",
                node_path=node.path(),
            )
        context = {
            "parent_path": parent.path(),
            "node": node_summary(node),
            "file_path": file_path,
            "format": detect_format(file_path),
        }
        if cook:
            try:
                node.cook(force=True)
                geo = node.geometry() if hasattr(node, "geometry") else None
                if geo is not None:
                    context["point_count"] = len(geo.points()) if hasattr(geo, "points") else None
                    context["primitive_count"] = len(geo.prims()) if hasattr(geo, "prims") else None
                context["warnings"] = list(node.warnings()) if hasattr(node, "warnings") else []
            except Exception as cook_exc:  # noqa: BLE001
                context["cook_error"] = str(cook_exc)
        return skill_success("Imported geometry", **context)
    except Exception as exc:
        return skill_exception(exc, message="Failed to import geometry")


@skill_entry
def main(**kwargs) -> dict:
    return import_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
