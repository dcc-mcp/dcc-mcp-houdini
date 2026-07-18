"""Export OBJ-level content to FBX via a /out Filmbox FBX ROP."""

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


def export_fbx(
    output_path: str,
    root_node: str = "/obj",
    frame_range: Optional[List[float]] = None,
    render: bool = True,
    create_dirs: bool = True,
) -> dict:
    """Create a Filmbox FBX ROP under /out and (optionally) render *root_node*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        # Validate the export root exists before building the ROP.
        get_node(hou, root_node)
        out = hou.node("/out")
        if out is None:
            out = hou.node("/").createNode("ropnet", node_name="out")
        rop = out.createNode("filmboxfbx", node_name="fbx_export")
        used = set_first_parm(rop, ("sopoutput", "filename", "outfile", "output"), output_path)
        # FBX ROP exports the subtree rooted at this node.
        set_first_parm(rop, ("startnode",), root_node)
        applied_range = apply_frame_range(rop, frame_range)
        if create_dirs:
            ensure_parent_dir(output_path)
        warnings: List[str] = []
        if used is None:
            warnings.append("Could not find an output-path parameter on filmboxfbx")
        if render and used is not None:
            try:
                rop.render()
            except Exception as render_exc:  # noqa: BLE001
                warnings.append("Render failed: {}".format(render_exc))
        written = [output_path] if os.path.isfile(output_path) else []
        skipped = [] if written else [output_path]
        return skill_success(
            "Exported FBX",
            root_node=root_node,
            rop=node_summary(rop),
            output_path=output_path,
            frame_range=applied_range,
            written_files=written,
            skipped=skipped,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export FBX")


@skill_entry
def main(**kwargs) -> dict:
    return export_fbx(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
