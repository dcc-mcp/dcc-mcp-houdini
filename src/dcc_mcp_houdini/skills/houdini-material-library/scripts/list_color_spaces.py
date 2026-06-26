"""List available OCIO color spaces from Houdini's active config (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _library_common import hou_import_error  # noqa: E402


def list_color_spaces(filter: Optional[str] = None) -> dict:
    """List available OCIO color spaces.

    Args:
        filter: Optional substring to filter color space names.

    Returns:
        ToolResult dict with color_spaces list.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        color_spaces = []

        # Houdini 20+ OCIO API.
        try:
            if hasattr(hou, "ocio") and hasattr(hou.ocio, "colorSpaces"):
                for cs in hou.ocio.colorSpaces():
                    name = cs.getName() if hasattr(cs, "getName") else str(cs)
                    if filter and filter.lower() not in name.lower():
                        continue
                    entry = {"name": name}
                    if hasattr(cs, "getFamily"):
                        family = cs.getFamily()
                        if family:
                            entry["family"] = family
                    if hasattr(cs, "getDescription"):
                        desc = cs.getDescription()
                        if desc:
                            entry["description"] = desc
                    color_spaces.append(entry)
            elif hasattr(hou, "color") and hasattr(hou.color, "colorSpaces"):
                # Older Houdini API.
                for cs_name in hou.color.colorSpaces():
                    if filter and filter.lower() not in cs_name.lower():
                        continue
                    color_spaces.append({"name": cs_name})
            else:
                # Fallback: try to list roles.
                if hasattr(hou, "color") and hasattr(hou.color, "roles"):
                    for role_name in hou.color.roles():
                        if filter and filter.lower() not in role_name.lower():
                            continue
                        color_spaces.append({"name": role_name, "type": "role"})
                else:
                    return skill_error(
                        "OCIO color space listing not available",
                        "Houdini version may not expose the OCIO API via HOM.",
                    )
        except Exception as exc:  # noqa: BLE001
            return skill_error(
                "Failed to list OCIO color spaces",
                str(exc),
            )

        return skill_success(
            "Listed OCIO color spaces",
            count=len(color_spaces),
            filter=filter,
            color_spaces=color_spaces,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list color spaces")


@skill_entry
def main(**kwargs) -> dict:
    return list_color_spaces(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
