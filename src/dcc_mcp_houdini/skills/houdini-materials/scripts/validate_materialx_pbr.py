"""Validate a MaterialX PBR material network without mutating it."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _material_common import get_node, hou_import_error, node_summary

_CHANNELS = ("base_color", "roughness", "metallic", "normal", "displacement")


def _input_source(node: Any, input_name: str) -> Optional[Any]:
    names = list(node.inputNames())
    if input_name not in names:
        return None
    index = names.index(input_name)
    inputs = list(node.inputs())
    return inputs[index] if index < len(inputs) else None


def validate_materialx_pbr(material_path: str, required_channels: Optional[Sequence[str]] = None) -> dict:
    """Inspect the standard surface, outputs, and requested texture channels."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        material = get_node(hou, material_path)
        issues = []
        if material.userData("dcc_mcp_material_schema") != "materialx_pbr_v1":
            issues.append("Material is not marked as a dcc-mcp MaterialX PBR network")

        surface = material.node("standard_surface")
        surface_output = material.node("surface_output")
        displacement_output = material.node("displacement_output")
        if surface is None or not surface.type().name().startswith("mtlxstandard_surface"):
            issues.append("Missing MaterialX standard surface")
        surface_source = None
        if surface_output is not None and surface_output.inputs():
            surface_source = surface_output.inputs()[0]
        if surface is None or surface_source is None or surface_source.path() != surface.path():
            issues.append("Standard surface is not connected to the surface output")

        channels: Dict[str, str] = {}
        if surface is not None:
            for channel, input_name in (
                ("base_color", "base_color"),
                ("roughness", "specular_roughness"),
                ("metallic", "metalness"),
            ):
                source = _input_source(surface, input_name)
                if source is not None:
                    channels[channel] = source.path()

            normal_map = _input_source(surface, "normal")
            if normal_map is not None:
                normal_source = _input_source(normal_map, "in")
                if normal_source is not None:
                    channels["normal"] = normal_source.path()

        if displacement_output is not None and displacement_output.inputs():
            displacement = displacement_output.inputs()[0]
            if displacement is not None:
                displacement_source = _input_source(displacement, "displacement")
                if displacement_source is not None:
                    channels["displacement"] = displacement_source.path()

        for channel in required_channels or ():
            if channel not in _CHANNELS:
                issues.append("Unsupported required channel: {}".format(channel))
            elif channel not in channels:
                issues.append("Required channel is not connected: {}".format(channel))

        return skill_success(
            "Validated MaterialX PBR material",
            valid=not issues,
            material=node_summary(material),
            channels=channels,
            issues=issues,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate MaterialX PBR material")


@skill_entry
def main(**kwargs) -> dict:
    return validate_materialx_pbr(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
