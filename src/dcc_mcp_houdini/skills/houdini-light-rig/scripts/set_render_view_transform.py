"""Configure the OCIO view transform for the Houdini session's render view."""

from __future__ import annotations

import os
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _get_active_config():
    """Load the config named by OCIO, falling back to OCIO's current config."""
    import PyOpenColorIO as ocio  # noqa: PLC0415

    config_path = os.environ.get("OCIO")
    return ocio.Config.CreateFromFile(config_path) if config_path else ocio.GetCurrentConfig()


def _apply_houdini_color_settings(
    view_transform: str,
    display_device: str,
    color_space: Optional[str] = None,
) -> dict:
    """Apply color settings via Houdini's hou.color API or OCIO env var."""
    applied = {}
    warnings = []

    try:
        import hou  # noqa: PLC0415

        # Houdini 20+ has hou.color.setColorTransform
        try:
            if hasattr(hou, "color") and hasattr(hou.color, "setColorTransform"):
                hou.color.setColorTransform(view_transform, display_device)
                applied["method"] = "hou.color.setColorTransform"
                applied["view_transform"] = view_transform
                applied["display_device"] = display_device

                if color_space:
                    try:
                        hou.color.setColorSpace(color_space)
                        applied["color_space"] = color_space
                    except Exception:  # noqa: BLE001
                        warnings.append("Could not set color_space via hou.color.setColorSpace")
                return {"applied": applied, "warnings": warnings}
        except Exception:  # noqa: BLE001
            pass

        # Fallback: set OCIO env var
        _set_ocio_env(view_transform, display_device, color_space)
        applied["method"] = "OCIO_env_var"
        applied["view_transform"] = view_transform
        applied["display_device"] = display_device
        if color_space:
            applied["color_space"] = color_space
        return {"applied": applied, "warnings": warnings}

    except ImportError:
        # No hou at all — use env var only
        _set_ocio_env(view_transform, display_device, color_space)
        applied["method"] = "OCIO_env_var (no hou)"
        applied["view_transform"] = view_transform
        applied["display_device"] = display_device
        if color_space:
            applied["color_space"] = color_space
        return {"applied": applied, "warnings": warnings}


def _set_ocio_env(view_transform: str, display_device: str, color_space: Optional[str] = None) -> None:
    """Set OCIO-related environment variables."""
    os.environ["OCIO_VIEW_TRANSFORM"] = view_transform
    os.environ["OCIO_DISPLAY"] = display_device
    if color_space:
        os.environ["OCIO_COLOR_SPACE"] = color_space


def set_render_view_transform(
    view_transform: str,
    display_device: str = "Rec.1886 Rec.709 - Display",
    color_space: Optional[str] = None,
) -> dict:
    """Configure the OCIO view transform for render view color management.

    Attempts to set the view transform through Houdini's ``hou.color`` API
    first (Houdini 20+), falling back to ``OCIO_*`` environment variables.
    Reports the available transforms and displays for the active OCIO config.

    Args:
        view_transform: OCIO view transform name, e.g.
            ``"ACES 1.0 SDR-video"``, ``"sRGB"``, ``"Raw"``,
            ``"Un-tone-mapped"``.
        display_device: OCIO display device name. Default ``"sRGB"``.
        color_space: Optional OCIO color space for rendering
            (e.g. ``"ACEScg"``, ``"scene_linear"``).

    Returns:
        ToolResult with ``applied`` configuration and ``available_transforms``.
    """
    try:
        try:
            config = _get_active_config()
            available_displays = list(config.getDisplays())
            if display_device not in available_displays:
                return skill_error(
                    "Display device '{}' not found in OCIO config".format(display_device),
                    "Choose one of the active config's displays.",
                    available_displays=available_displays,
                )
            available_transforms = list(config.getViews(display_device))
            if color_space and config.getColorSpace(color_space) is None:
                return skill_error(
                    "Color space '{}' not found in OCIO config".format(color_space),
                    "Choose one of the active config's declared color spaces or roles.",
                    available_color_spaces=list(config.getColorSpaceNames()),
                )
        except Exception as exc:  # noqa: BLE001
            available_transforms = []
            available_displays = []
            config_warning = "PyOpenColorIO validation unavailable: {}".format(exc)
        else:
            config_warning = None

        if available_transforms and view_transform not in available_transforms:
            return skill_error(
                "View transform '{}' not found in OCIO config".format(view_transform),
                "Available transforms: {}".format(", ".join(available_transforms)),
                requested_transform=view_transform,
                available_transforms=available_transforms,
            )

        result = _apply_houdini_color_settings(view_transform, display_device, color_space)
        warnings = result.get("warnings") or []
        if config_warning:
            warnings.append(config_warning)

        return skill_success(
            "Set render view transform to '{}' ({})".format(view_transform, result["applied"].get("method", "unknown")),
            applied=result["applied"],
            available_transforms=available_transforms,
            available_displays=available_displays,
            warnings=warnings or None,
            prompt="Use get_lighting_summary to review the scene's lighting, then capture_viewport (houdini-render) to verify the render look.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set render view transform")


@skill_entry
def main(**kwargs) -> dict:
    return set_render_view_transform(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
