"""Install a Houdini Digital Asset library."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_common import definitions_in_file, hou_import_error, validate_hda_path


def install_hda_file(file_path: str) -> dict:
    """Install an HDA/OTL file into the current Houdini session."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        path = validate_hda_path(file_path, must_exist=True)
        hou.hda.installFile(str(path))
        definitions = definitions_in_file(hou, str(path))
        return skill_success(
            "Installed Houdini Digital Asset file",
            file_path=str(path),
            definitions=definitions,
            definition_count=len(definitions),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to install Houdini Digital Asset file")


@skill_entry
def main(**kwargs) -> dict:
    return install_hda_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
