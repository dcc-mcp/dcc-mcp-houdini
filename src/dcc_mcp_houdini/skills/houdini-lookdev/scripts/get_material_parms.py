"""Read parameter names and values for a material/shader node (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _lookdev_common import get_node, node_summary  # noqa: E402


def get_material_parms(material_path: str, name_filter: Optional[str] = None) -> dict:
    """Return evaluated parameter values for the material at *material_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, material_path)
        parms = []
        for parm in node.parms():
            name = parm.name()
            if name_filter and name_filter.lower() not in name.lower():
                continue
            try:
                value = parm.eval()
            except Exception:  # noqa: BLE001
                value = None
            parms.append({"name": name, "value": value})
        return skill_success(
            "Read material parameters",
            material=node_summary(node),
            count=len(parms),
            parameters=parms,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read material parameters")


@skill_entry
def main(**kwargs) -> dict:
    return get_material_parms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
