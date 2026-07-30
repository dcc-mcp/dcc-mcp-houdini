"""List available OCIO color spaces from Houdini's active config (read-only)."""

from __future__ import annotations

import os
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_color_spaces(filter: Optional[str] = None) -> dict:
    """List available OCIO color spaces.

    Args:
        filter: Optional substring to filter color space names.

    Returns:
        ToolResult dict with color_spaces list.
    """
    try:
        try:
            import PyOpenColorIO as ocio  # noqa: PLC0415

            config_path = os.environ.get("OCIO")
            config = ocio.Config.CreateFromFile(config_path) if config_path else ocio.GetCurrentConfig()
            color_spaces = []
            for name in config.getColorSpaceNames():
                if filter and filter.lower() not in name.lower():
                    continue
                color_space = config.getColorSpace(name)
                entry = {"name": name}
                family = color_space.getFamily() if color_space is not None else ""
                if family:
                    entry["family"] = family
                color_spaces.append(entry)
            source = "PyOpenColorIO"
        except Exception as ocio_exc:  # noqa: BLE001
            try:
                import hou  # noqa: PLC0415

                color_spaces = []
                if hasattr(hou, "ocio") and hasattr(hou.ocio, "colorSpaces"):
                    names = hou.ocio.colorSpaces()
                elif hasattr(hou, "color") and hasattr(hou.color, "colorSpaces"):
                    names = hou.color.colorSpaces()
                else:
                    return skill_error(
                        "OCIO color space listing not available",
                        "PyOpenColorIO: {}; Houdini exposes no color-space listing API.".format(ocio_exc),
                    )
                for color_space in names:
                    name = color_space.getName() if hasattr(color_space, "getName") else str(color_space)
                    if not filter or filter.lower() in name.lower():
                        color_spaces.append({"name": name})
                config_path = os.environ.get("OCIO")
                source = "HOM"
            except Exception as hom_exc:  # noqa: BLE001
                return skill_error(
                    "Failed to list OCIO color spaces",
                    "PyOpenColorIO: {}; HOM: {}".format(ocio_exc, hom_exc),
                )

        return skill_success(
            "Listed OCIO color spaces",
            count=len(color_spaces),
            filter=filter,
            color_spaces=color_spaces,
            source=source,
            ocio_config_path=config_path,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list color spaces")


@skill_entry
def main(**kwargs) -> dict:
    return list_color_spaces(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
