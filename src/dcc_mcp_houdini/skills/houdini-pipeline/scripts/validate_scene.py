"""Validate a hip scene: missing files, dirty state, and cook warnings."""

from __future__ import annotations

import os
from typing import List, Optional

from _pipeline_common import expand_path, iter_file_parms, resolve_nodes  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def validate_scene(
    node_paths: Optional[List[str]] = None,
    check_outputs: bool = True,
) -> dict:
    """Report missing input files, unwritable output dirs, dirty state, errors.

    Scans file-reference parms across the scene (or *node_paths*). Output-driver
    parms whose directory does not yet exist are reported as actionable issues
    rather than hard failures.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        missing_files: List[dict] = []
        bad_output_dirs: List[dict] = []
        node_errors: List[dict] = []
        nodes = resolve_nodes(hou, node_paths)

        for node in nodes:
            for parm in iter_file_parms(hou, node):
                raw = parm.eval()
                resolved = expand_path(hou, raw)
                # Heuristic: output parms usually live on rop/sop "sopoutput"-style names.
                name = parm.name().lower()
                is_output = any(tok in name for tok in ("output", "sopoutput", "picture", "vm_picture", "lopoutput"))
                if is_output and check_outputs:
                    out_dir = os.path.dirname(resolved)
                    if out_dir and not os.path.isdir(out_dir):
                        bad_output_dirs.append({"node": node.path(), "parm": parm.name(), "dir": out_dir})
                    continue
                if not os.path.exists(resolved):
                    missing_files.append({"node": node.path(), "parm": parm.name(), "path": resolved})
            try:
                errs = list(node.errors()) if hasattr(node, "errors") else []
            except Exception:  # noqa: BLE001
                errs = []
            if errs:
                node_errors.append({"node": node.path(), "errors": errs})

        try:
            dirty = bool(hou.hipFile.hasUnsavedChanges())
        except Exception:  # noqa: BLE001
            dirty = None

        issue_count = len(missing_files) + len(bad_output_dirs) + len(node_errors)
        valid = issue_count == 0
        return skill_success(
            "Scene is valid" if valid else "Scene validation found issues",
            valid=valid,
            scanned_nodes=len(nodes),
            dirty=dirty,
            missing_files=missing_files,
            bad_output_dirs=bad_output_dirs,
            node_errors=node_errors,
            issue_count=issue_count,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate scene")


@skill_entry
def main(**kwargs) -> dict:
    return validate_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
