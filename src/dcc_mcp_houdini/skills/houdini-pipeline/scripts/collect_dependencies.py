"""Collect external file dependencies for a hip scene or selected nodes."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _pipeline_common import expand_path, iter_file_parms, resolve_nodes  # noqa: E402


def collect_dependencies(node_paths: Optional[List[str]] = None) -> dict:
    """Return a dependency manifest. Never copies files (manifest only).

    Each entry records the referencing node, parameter, raw value, resolved
    path, and whether the file currently exists on disk.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        nodes = resolve_nodes(hou, node_paths)
        dependencies: List[dict] = []
        seen = set()
        for node in nodes:
            for parm in iter_file_parms(hou, node):
                raw = parm.eval()
                resolved = expand_path(hou, raw)
                dedupe_key = (node.path(), parm.name(), resolved)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                dependencies.append(
                    {
                        "node": node.path(),
                        "parm": parm.name(),
                        "raw": raw,
                        "resolved": resolved,
                        "exists": os.path.exists(resolved),
                    }
                )
        missing = [d for d in dependencies if not d["exists"]]
        return skill_success(
            "Collected dependencies",
            scanned_nodes=len(nodes),
            count=len(dependencies),
            missing_count=len(missing),
            dependencies=dependencies,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to collect dependencies")


@skill_entry
def main(**kwargs) -> dict:
    return collect_dependencies(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
