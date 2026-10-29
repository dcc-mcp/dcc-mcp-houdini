"""Export a SOP node's geometry to a native/interchange file via saveToFile."""

from __future__ import annotations

import os

from _io_common import detect_format, ensure_parent_dir, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def export_geometry(
    node_path: str,
    output_path: str,
    create_dirs: bool = True,
) -> dict:
    """Write the cooked geometry of *node_path* to *output_path*.

    Uses ``hou.Geometry.saveToFile`` which supports native (.bgeo/.geo),
    .obj, .ply, and other formats recognised by the installed runtime.
    """
    # ``Geometry.saveToFile`` cannot author USD. Detect a USD suffix up front so
    # we never write silently-invalid bytes to a .usd path; point the caller at
    # the typed SOP-to-USD bridge instead.
    fmt = detect_format(output_path)
    if fmt == "usd":
        return skill_error(
            "USD suffix not supported by saveToFile",
            "export_geometry cannot author USD; use export_sop_to_usd",
            prompt=(
                "Author USD from this SOP with houdini_interchange__export_sop_to_usd, "
                "or export a composed LOP stage with houdini_interchange__export_usd."
            ),
            possible_solutions=[
                "Use houdini_interchange__export_sop_to_usd(node_path=...) for a SOP node.",
                "Use houdini_interchange__export_usd(lop_node_path=...) for a LOP stage.",
            ],
            dcc={"next_tools": ["houdini_interchange__export_sop_to_usd"]},
            format=fmt,
            node_path=node_path,
            output_path=output_path,
        )

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        geo = node.geometry() if hasattr(node, "geometry") else None
        if geo is None:
            return skill_error(
                "No SOP geometry",
                "Node has no geometry to export",
                node_path=node.path(),
            )
        if create_dirs:
            ensure_parent_dir(output_path)
        geo.saveToFile(output_path)
        written = [output_path] if os.path.isfile(output_path) else []
        skipped = [] if written else [output_path]
        return skill_success(
            "Exported geometry",
            node_path=node.path(),
            output_path=output_path,
            format=detect_format(output_path),
            written_files=written,
            skipped=skipped,
            warnings=[],
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export geometry")


@skill_entry
def main(**kwargs) -> dict:
    return export_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
