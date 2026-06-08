"""Configure Houdini's OCIO color management settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _library_common import hou_import_error  # noqa: E402


def set_color_management(
    ocio_config_path: Optional[str] = None,
    color_space: Optional[str] = None,
    view_transform: Optional[str] = None,
) -> dict:
    """Configure Houdini OCIO color management.

    Args:
        ocio_config_path: Path to an OCIO config.ocio file.
        color_space: Default color space name (e.g. ACEScg).
        view_transform: View transform name (e.g. Un-tone-mapped).

    Returns:
        ToolResult dict.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    changes: dict = {}
    warnings: list = []

    # --- Set OCIO config path ---
    if ocio_config_path:
        config_path = Path(ocio_config_path)
        if not config_path.is_file():
            return skill_error(
                "OCIO config not found: {}".format(ocio_config_path),
                "Provide a valid path to a config.ocio file.",
            )
        try:
            os.environ["OCIO"] = str(config_path)
            changes["ocio_config_path"] = str(config_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append("Failed to set OCIO env: {}".format(exc))

    # --- Set color space / view transform via HOM ---
    # Houdini 20+ exposes hou.Color.oclo; older versions use env vars.
    try:
        if color_space:
            # Try Houdini 20+ color management API.
            try:
                if hasattr(hou, "ocio") and hasattr(hou.ocio, "setDefaultColorSpace"):
                    hou.ocio.setDefaultColorSpace(color_space)
                    changes["color_space"] = color_space
                else:
                    os.environ["OCIO_COLOR_SPACE"] = color_space
                    changes["color_space"] = color_space
            except Exception:  # noqa: BLE001
                os.environ["OCIO_COLOR_SPACE"] = color_space
                changes["color_space"] = color_space
                warnings.append("Set via env var (HOM API unavailable)")

        if view_transform:
            try:
                if hasattr(hou, "ocio") and hasattr(hou.ocio, "setDefaultViewTransform"):
                    hou.ocio.setDefaultViewTransform(view_transform)
                    changes["view_transform"] = view_transform
                else:
                    os.environ["OCIO_VIEW_TRANSFORM"] = view_transform
                    changes["view_transform"] = view_transform
            except Exception:  # noqa: BLE001
                os.environ["OCIO_VIEW_TRANSFORM"] = view_transform
                changes["view_transform"] = view_transform
                warnings.append("Set via env var (HOM API unavailable)")
    except Exception as exc:  # noqa: BLE001
        warnings.append("Color management API error: {}".format(exc))

    if not changes:
        return skill_error(
            "No color management settings provided",
            "Specify at least one of: ocio_config_path, color_space, view_transform.",
        )

    return skill_success(
        "Updated color management settings",
        changes=changes,
        warnings=warnings if warnings else None,
        note="A Houdini restart or refresh may be needed for env-var changes to take full effect.",
    )


@skill_entry
def main(**kwargs) -> dict:
    return set_color_management(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
