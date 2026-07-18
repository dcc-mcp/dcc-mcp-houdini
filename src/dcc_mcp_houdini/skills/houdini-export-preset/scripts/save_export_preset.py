"""Save a ROP node's export configuration as a JSON preset in a library directory."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import _export_preset_common  # noqa: E402
from _export_preset_common import (  # noqa: E402
    detect_format_from_type,
    find_rop_in_out,
    find_source_path,
    get_node,
    hou_import_error,
    node_summary,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name).strip("_")
    return cleaned or "preset"


def save_export_preset(
    preset_name: str,
    rop_node_path: Optional[str] = None,
    source_node_path: Optional[str] = None,
    format: Optional[str] = None,
    library_dir: Optional[str] = None,
    overwrite: bool = True,
    custom_settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Save a ROP node's export configuration as a JSON preset.

    Args:
        preset_name: Name for the preset file (stem without .json).
        rop_node_path: Path to the ROP node whose config to capture.
        source_node_path: Path to the SOP/LOP node to export (auto-discovery
            fallback when rop_node_path is omitted).
        format: Export format hint.  Auto-detected when omitted.
        library_dir: Directory for preset files.
        overwrite: If False and the file exists, return an error.
        custom_settings: Extra key-value pairs to merge into the preset.

    Returns:
        ToolResult dict with preset_path, preset_data, and rop info.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        # Resolve ROP node.
        if rop_node_path:
            rop_node = get_node(hou, rop_node_path)
        elif source_node_path:
            rop_node = find_rop_in_out(hou, source_node_path)
            if rop_node is None:
                return skill_error(
                    "No ROP node found for source: {}".format(source_node_path),
                    "Specify rop_node_path explicitly or ensure a ROP in /out references this source node.",
                )
        else:
            rop_node = find_rop_in_out(hou)
            if rop_node is None:
                return skill_error(
                    "No ROP node found in /out",
                    "Specify rop_node_path or source_node_path.",
                )

        # Determine the file path.
        base = _export_preset_common.library_dir(library_dir)
        safe_stem = _safe_name(preset_name)
        file_path = base / "{}.json".format(safe_stem)

        if not overwrite and file_path.exists():
            return skill_error(
                "Preset {!r} already exists at {}".format(safe_stem, file_path),
                "Set overwrite=True to replace it.",
            )

        # Collect ROP parameters (skipping read-only/internal ones).
        rop_type = rop_node.type().name() if hasattr(rop_node.type(), "name") else ""
        export_format = format or detect_format_from_type(rop_type)
        resolved_source = source_node_path or find_source_path(rop_node)

        # Capture frame range from the scene timeline.
        frame_range = None
        try:
            frame_range = [
                int(hou.playbar.playbackRange()[0]),
                int(hou.playbar.playbackRange()[1]),
            ]
        except Exception:  # noqa: BLE001
            pass

        # Capture all settable ROP parameters.
        parameters: Dict[str, Any] = {}
        skip_parms = {"caching", "frozen", "isHistoricallyInteresting", "nodeState"}
        for parm in rop_node.parms():
            name = parm.name()
            if name in skip_parms or "." in name:
                continue
            try:
                value = parm.eval()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(value, tuple):
                value = list(value)
            parameters[name] = value

        preset_data: Dict[str, Any] = {
            "preset_name": preset_name,
            "format": export_format,
            "rop_type": rop_type,
            "rop_parameters": parameters,
            "frame_range": frame_range,
            "source_node_path": resolved_source,
            "rop_node_summary": node_summary(rop_node),
        }

        if custom_settings:
            preset_data.update(custom_settings)

        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(preset_data, handle, indent=2)

        return skill_success(
            "Saved export preset",
            preset_name=preset_name,
            format=export_format,
            rop_type=rop_type,
            source_node_path=resolved_source,
            parameter_count=len(parameters),
            frame_range=frame_range,
            preset_path=str(file_path),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to save export preset")


@skill_entry
def main(**kwargs) -> dict:
    return save_export_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
