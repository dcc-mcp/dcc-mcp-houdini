"""Save a Houdini node as a Digital Asset."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_common import hou_import_error, node_summary, validate_hda_path


def save_node_as_hda(
    node_path: str,
    hda_file_path: str,
    hda_name: str,
    label: Optional[str] = None,
    version: Optional[str] = None,
    save_as_embedded: bool = False,
) -> dict:
    """Create and save a digital asset from an existing node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node not found: {}".format(node_path))
        hda_path = validate_hda_path(hda_file_path, must_exist=False)
        hda_node = node.createDigitalAsset(
            name=hda_name,
            hda_file_name=str(hda_path),
            description=label or hda_name,
            version=version,
            save_as_embedded=save_as_embedded,
        )
        definition = hda_node.type().definition()
        if definition is not None and hasattr(definition, "save"):
            definition.save(str(hda_path))
        return skill_success(
            "Saved Houdini node as Digital Asset",
            source_node=node_path,
            hda_node=node_summary(hda_node),
            hda_file_path=str(hda_path),
            hda_name=hda_name,
            version=version,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to save Houdini node as Digital Asset")


@skill_entry
def main(**kwargs) -> dict:
    return save_node_as_hda(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
