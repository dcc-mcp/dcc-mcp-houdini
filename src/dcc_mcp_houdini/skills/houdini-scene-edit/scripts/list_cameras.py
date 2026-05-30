"""List camera object nodes in the scene."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _scene_edit_common import get_node, iter_nodes, node_summary  # noqa: E402


def list_cameras(root_path: str = "/obj", recursive: bool = True) -> dict:
    """List object-level camera nodes (type name contains ``cam``)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        root = get_node(hou, root_path)
        cameras = []
        for node in iter_nodes(root, recursive):
            type_name = node.type().name()
            # Match 'cam' but skip 'camera switcher'-style helpers via exact-ish check.
            if type_name == "cam" or type_name.startswith("cam"):
                cameras.append(node_summary(node))
        return skill_success(
            "Listed cameras",
            cameras=cameras,
            count=len(cameras),
            root_path=root_path,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list cameras")


@skill_entry
def main(**kwargs) -> dict:
    return list_cameras(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
