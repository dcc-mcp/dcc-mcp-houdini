"""List image/file-texture nodes in the scene (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _library_common import (  # noqa: E402
    find_image_filepath,
    get_node,
    hou_import_error,
    is_image_node,
    iter_nodes_recursive,
)


def list_images(parent_path: str = "/mat") -> dict:
    """List image/file-texture nodes under *parent_path*.

    Args:
        parent_path: Material network to scan (e.g. /mat or /obj).

    Returns:
        ToolResult dict with a list of image node info dicts.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        parent = get_node(hou, parent_path)
        images: List[dict] = []
        missing_files: List[dict] = []

        for node in iter_nodes_recursive(parent):
            if not is_image_node(node):
                continue
            info = {
                "path": node.path(),
                "name": node.name(),
                "type": node.type().name() if hasattr(node.type(), "name") else str(node.type()),
            }
            filepath = find_image_filepath(node)
            if filepath:
                info["file_path"] = filepath
                fp = Path(filepath)
                info["exists_on_disk"] = fp.is_file()
                if not fp.is_file():
                    missing_files.append(info.copy())
            else:
                info["file_path"] = None
                info["exists_on_disk"] = False

            # Try to get resolution info.
            try:
                res_parm = node.parm("resolution")
                if res_parm is not None:
                    res_val = res_parm.eval()
                    info["resolution"] = res_val
            except Exception:  # noqa: BLE001
                pass

            images.append(info)

        return skill_success(
            "Listed image nodes",
            parent_path=parent.path(),
            total_count=len(images),
            missing_count=len(missing_files),
            images=images,
            missing_files=missing_files if missing_files else None,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list images")


@skill_entry
def main(**kwargs) -> dict:
    return list_images(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
