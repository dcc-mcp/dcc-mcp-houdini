"""Load a saved export preset from the library and optionally create a ROP node."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import _export_preset_common  # noqa: E402
from _export_preset_common import (  # noqa: E402
    get_node,
    hou_import_error,
    node_summary,
)


def load_export_preset(
    preset_name: str,
    library_dir: Optional[str] = None,
    create_rop: bool = False,
    rop_parent_path: str = "/out",
    source_node_path: Optional[str] = None,
    connect_source: bool = False,
) -> dict:
    """Load a saved export preset from the library.

    Args:
        preset_name: Name of the preset to load (stem without .json).
        library_dir: Directory containing .json preset files.
        create_rop: When true, create a ROP node from the preset.
        rop_parent_path: Parent network for the created ROP node.
        source_node_path: Override the source node path in the preset.
        connect_source: Wire the created ROP to the source node.

    Returns:
        ToolResult dict with preset_data, and optional created_rop info.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        base = _export_preset_common.library_dir(library_dir)
        target = base / "{}.json".format(preset_name)

        if not target.is_file():
            # Fuzzy match.
            candidates = list(base.glob("*.json"))
            for candidate in candidates:
                if candidate.stem == preset_name:
                    target = candidate
                    break
            else:
                return skill_error(
                    "Export preset not found: {!r}".format(preset_name),
                    "Use list_export_presets to find available preset names.",
                    library_dir=str(base),
                )

        try:
            with open(target, encoding="utf-8") as handle:
                preset_data = json.load(handle)
        except (IOError, ValueError) as exc:
            return skill_error(
                "Cannot read export preset {!r}".format(str(target)),
                str(exc),
            )

        result_fields: Dict[str, Any] = {
            "preset_name": preset_name,
            "file_path": str(target),
            "format": preset_data.get("format"),
            "rop_type": preset_data.get("rop_type"),
            "parameters": preset_data.get("rop_parameters", {}),
            "frame_range": preset_data.get("frame_range"),
            "source_node_path": preset_data.get("source_node_path"),
        }

        active_source = source_node_path or preset_data.get("source_node_path")

        # Optionally create a ROP node from the preset.
        if create_rop:
            rop_type = preset_data.get("rop_type", "geometry")
            parent = get_node(hou, rop_parent_path)
            rop_node = parent.createNode(rop_type, node_name="{}_preset".format(preset_name))

            # Apply saved parameters.
            parameters = preset_data.get("rop_parameters", {})
            applied = 0
            errors: Dict[str, str] = {}
            for name, value in parameters.items():
                try:
                    if isinstance(value, (list, tuple)):
                        parm_tuple = rop_node.parmTuple(name)
                        if parm_tuple is not None:
                            parm_tuple.set(tuple(value))
                            applied += 1
                            continue
                    parm = rop_node.parm(name)
                    if parm is not None:
                        parm.set(value)
                        applied += 1
                except Exception as exc:  # noqa: BLE001
                    errors[name] = str(exc)

            # Wire to source node if requested.
            connected = False
            if connect_source and active_source:
                for parm_name in ("soppath", "loppath", "sop_path", "lop_path"):
                    parm = rop_node.parm(parm_name)
                    if parm is not None:
                        try:
                            parm.set(str(active_source))
                            connected = True
                            break
                        except Exception:  # noqa: BLE001
                            pass

            result_fields["created_rop"] = node_summary(rop_node)
            result_fields["applied_count"] = applied
            result_fields["errors"] = errors if errors else None
            result_fields["connected_source"] = connected

            # Try to set output path based on the preset's output parameter.
            if "sopoutput" in parameters:
                out_parm = rop_node.parm("sopoutput")
                if out_parm is not None:
                    try:
                        out_parm.set(parameters["sopoutput"])
                    except Exception:  # noqa: BLE001
                        pass

        return skill_success(
            "Loaded export preset",
            **result_fields,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to load export preset")


@skill_entry
def main(**kwargs) -> dict:
    return load_export_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
