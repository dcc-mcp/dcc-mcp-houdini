"""List Houdini Digital Asset definitions."""

from __future__ import annotations

from typing import Optional

from _hda_common import definition_summary, definitions_in_file, hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def list_hda_definitions(file_path: Optional[str] = None) -> dict:
    """List HDA definitions from a file or all loaded HDA libraries."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        if file_path:
            definitions = definitions_in_file(hou, file_path)
            files = [file_path]
        else:
            files = list(hou.hda.loadedFiles())
            definitions = []
            for loaded_file in files:
                try:
                    definitions.extend(
                        definition_summary(defn, loaded_file) for defn in hou.hda.definitionsInFile(loaded_file)
                    )
                except Exception:
                    continue
        return skill_success(
            "Listed Houdini Digital Asset definitions",
            files=files,
            definitions=definitions,
            definition_count=len(definitions),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list Houdini Digital Asset definitions")


@skill_entry
def main(**kwargs) -> dict:
    return list_hda_definitions(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
