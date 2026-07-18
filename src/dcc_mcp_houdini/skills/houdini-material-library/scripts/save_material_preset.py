"""Save a material/shader node's definition as a JSON preset in a library directory."""

from __future__ import annotations

import json
import re
from typing import List, Optional

import _library_common  # noqa: E402
from _library_common import get_node, hou_import_error, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")

# Parameters to skip during serialization (read-only / internal).
_SKIP_PARMS = {
    "caching",
    "frozen",
    "isHistoricallyInteresting",
    "nodeState",
    "display",
    "renderable",
    "visible",
    "picking",
    "unload",
    "dirty",
    "bypass",
}


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name).strip("_")
    return cleaned or "preset"


def save_material_preset(
    material_path: str,
    preset_name: str,
    library_dir: Optional[str] = None,
    attributes: Optional[List[str]] = None,
    overwrite: bool = True,
) -> dict:
    """Serialize *material_path*'s definition to a JSON preset file.

    Args:
        material_path: Path to the material/shader node.
        preset_name: File name stem (without .json).
        library_dir: Directory for preset files.
        attributes: Explicit list of parameter names to capture.
        overwrite: If False and the file exists, return an error.

    Returns:
        ToolResult dict with file_path, node_type, and parameter_count.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        node = get_node(hou, material_path)
        base = _library_common.library_dir(library_dir)
        safe_stem = _safe_name(preset_name)
        file_path = base / "{}.json".format(safe_stem)

        if not overwrite and file_path.exists():
            return skill_error(
                "Preset {!r} already exists at {}".format(safe_stem, file_path),
                "Set overwrite=True to replace it.",
            )

        parameters = {}
        source_parms = node.parms()
        wanted = set(attributes) if attributes else None
        for parm in source_parms:
            name = parm.name()
            if wanted is not None and name not in wanted:
                continue
            if name in _SKIP_PARMS or "." in name:
                continue
            try:
                value = parm.eval()
            except Exception:  # noqa: BLE001
                continue
            # Convert tuples to lists for JSON serialization.
            if isinstance(value, tuple):
                value = list(value)
            parameters[name] = value

        preset_data = {
            "preset_name": preset_name,
            "material_path": material_path,
            "material_type": node.type().name(),
            "parameters": parameters,
        }

        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(preset_data, handle, indent=2)

        return skill_success(
            "Saved material preset",
            preset_name=preset_name,
            material=node_summary(node),
            parameter_count=len(parameters),
            preset_path=str(file_path),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to save material preset")


@skill_entry
def main(**kwargs) -> dict:
    return save_material_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
