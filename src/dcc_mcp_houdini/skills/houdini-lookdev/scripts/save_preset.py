"""Save a material's parameter values as an adapter-owned JSON preset."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _lookdev_common import get_node, preset_dir  # noqa: E402

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name).strip("_")
    return cleaned or "preset"


def save_preset(
    material_path: str,
    preset_name: str,
    parm_names: Optional[List[str]] = None,
) -> dict:
    """Write a JSON preset of *material_path*'s parameter values."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, material_path)
        parameters = {}
        source_parms = node.parms()
        wanted = set(parm_names) if parm_names else None
        for parm in source_parms:
            name = parm.name()
            if wanted is not None and name not in wanted:
                continue
            try:
                parameters[name] = parm.eval()
            except Exception:  # noqa: BLE001
                continue
        payload = {
            "preset_name": preset_name,
            "material_type": node.type().name(),
            "parameters": parameters,
        }
        target = preset_dir() / "{}.json".format(_safe_name(preset_name))
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return skill_success(
            "Saved material preset",
            preset_name=preset_name,
            material_type=payload["material_type"],
            parameter_count=len(parameters),
            preset_path=str(target),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to save material preset")


@skill_entry
def main(**kwargs) -> dict:
    return save_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
