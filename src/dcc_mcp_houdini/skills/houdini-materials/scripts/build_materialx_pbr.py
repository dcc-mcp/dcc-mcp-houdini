"""Build a standard MaterialX PBR material network."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _material_common import get_node, hou_import_error, node_summary


def _set_value(node: Any, name: str, value: Any) -> None:
    if isinstance(value, (list, tuple)):
        parm_tuple = node.parmTuple(name)
        if parm_tuple is not None:
            parm_tuple.set(tuple(value))
            return
    parm = node.parm(name)
    if parm is None:
        raise ValueError("Parameter {!r} not found on {}".format(name, node.path()))
    parm.set(value)


def _connect(target: Any, input_name: str, source: Any) -> None:
    names = list(target.inputNames())
    try:
        index = names.index(input_name)
    except ValueError:
        raise ValueError("Input {!r} not found on {}".format(input_name, target.path())) from None
    target.setInput(index, source, 0)


def _image(builder: Any, name: str, file_path: str, signature: str, color_space: str) -> Any:
    image = builder.createNode("mtlximage", node_name=name)
    _set_value(image, "signature", signature)
    _set_value(image, "file", file_path)
    _set_value(image, "filecolorspace", color_space)
    return image


def build_materialx_pbr(
    parent_path: str = "/mat",
    material_name: str = "materialx_pbr",
    base_color: Sequence[float] = (0.18, 0.18, 0.18),
    roughness: float = 0.5,
    metallic: float = 0.0,
    base_color_texture: Optional[str] = None,
    roughness_texture: Optional[str] = None,
    metallic_texture: Optional[str] = None,
    normal_texture: Optional[str] = None,
    displacement_texture: Optional[str] = None,
    normal_scale: float = 1.0,
    displacement_scale: float = 0.01,
    base_color_space: str = "srgb_texture",
    data_color_space: str = "Raw",
) -> dict:
    """Create and wire a Karma-compatible MaterialX standard-surface material."""
    try:
        import hou  # noqa: PLC0415
        import voptoolutils  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    material = None
    try:
        parent = get_node(hou, parent_path)
        material = parent.createNode("subnet", node_name=material_name)
        voptoolutils._setupMtlXBuilderSubnet(material, "kma")

        surface = material.node("mtlxstandard_surface")
        if surface is None:
            surface = material.createNode("mtlxstandard_surface", node_name="standard_surface")
        else:
            surface.setName("standard_surface", unique_name=True)
        _set_value(surface, "base_color", base_color)
        _set_value(surface, "specular_roughness", roughness)
        _set_value(surface, "metalness", metallic)

        surface_output = material.node("surface_output")
        displacement_output = material.node("displacement_output")
        if surface_output is None or displacement_output is None:
            raise RuntimeError("MaterialX builder outputs were not created")
        surface_output.setInput(0, surface, 0)

        channels: Dict[str, str] = {}
        texture_specs: Tuple[Tuple[str, Optional[str], str, str], ...] = (
            ("base_color", base_color_texture, "color3", base_color_space),
            ("roughness", roughness_texture, "float", data_color_space),
            ("metallic", metallic_texture, "float", data_color_space),
        )
        input_names = {
            "base_color": "base_color",
            "roughness": "specular_roughness",
            "metallic": "metalness",
        }
        for channel, file_path, signature, color_space in texture_specs:
            if not file_path:
                continue
            image = _image(material, channel + "_texture", file_path, signature, color_space)
            _connect(surface, input_names[channel], image)
            channels[channel] = image.path()

        if normal_texture:
            normal_image = _image(material, "normal_texture", normal_texture, "color3", data_color_space)
            normal_map = material.createNode("mtlxnormalmap", node_name="normal_map")
            _set_value(normal_map, "scale", normal_scale)
            _connect(normal_map, "in", normal_image)
            _connect(surface, "normal", normal_map)
            channels["normal"] = normal_image.path()

        displacement = material.node("mtlxdisplacement")
        if displacement is None:
            displacement = material.createNode("mtlxdisplacement", node_name="displacement")
        else:
            displacement.setName("displacement", unique_name=True)
        if displacement_texture:
            displacement_image = _image(
                material,
                "displacement_texture",
                displacement_texture,
                "float",
                data_color_space,
            )
            _set_value(displacement, "scale", displacement_scale)
            _connect(displacement, "displacement", displacement_image)
            displacement_output.setInput(0, displacement, 0)
            channels["displacement"] = displacement_image.path()

        material.setUserData("dcc_mcp_material_schema", "materialx_pbr_v1")
        material.setUserData("dcc_mcp_material_channels", ",".join(sorted(channels)))
        material.layoutChildren()
        return skill_success(
            "Built MaterialX PBR material",
            valid=True,
            material=node_summary(material),
            standard_surface=surface.path(),
            channels=channels,
        )
    except Exception as exc:
        if material is not None:
            try:
                material.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(exc, message="Failed to build MaterialX PBR material")


@skill_entry
def main(**kwargs) -> dict:
    return build_materialx_pbr(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
