"""Export a SOP stream to Alembic via a ROP Alembic Output SOP."""

from __future__ import annotations

import os
from typing import List, Optional

from _io_common import (  # noqa: E402
    apply_frame_range,
    ensure_parent_dir,
    get_node,
    node_summary,
    set_first_parm,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def export_alembic(
    node_path: str,
    output_path: str,
    frame_range: Optional[List[float]] = None,
    render: bool = True,
    create_dirs: bool = True,
) -> dict:
    """Append a ROP Alembic Output SOP to *node_path* and (optionally) render."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, node_path)
        parent = source.parent()
        if parent is None:
            return skill_error("No parent network", "Input has no parent network")
        rop = parent.createNode("rop_alembic", node_name="abc_export")
        rop.setInput(0, source)
        used = set_first_parm(rop, ("filename", "abcoutput", "sopoutput"), output_path)
        applied_range = apply_frame_range(rop, frame_range)
        if create_dirs:
            ensure_parent_dir(output_path)
        warnings: List[str] = []
        if used is None:
            warnings.append("Could not find an output-path parameter on rop_alembic")
        if render and used is not None:
            try:
                rop.render()
            except Exception as render_exc:  # noqa: BLE001
                warnings.append("Render failed: {}".format(render_exc))
        written = [output_path] if os.path.isfile(output_path) else []
        skipped = [] if written else [output_path]
        return skill_success(
            "Exported Alembic",
            node_path=source.path(),
            rop=node_summary(rop),
            output_path=output_path,
            frame_range=applied_range,
            written_files=written,
            skipped=skipped,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export Alembic")


@skill_entry
def main(**kwargs) -> dict:
    return export_alembic(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
