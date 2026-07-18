"""Multi-map texture baking via Labs Maps Baker or Bake Texture ROP.

Supports 20+ map types when Labs Maps Baker is installed, or the standard
subset available through the Bake Texture ROP.
"""

from __future__ import annotations

import os
from typing import List, Optional

from _texture_bake_common import (  # noqa: E402
    collect_geometry,
    create_or_get_bake_rop,
    detect_bake_methods,
    set_parm_if_exists,
    validate_map_types,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_DEFAULT_MAP_TYPES = ["normals", "cavity", "curvature", "diffuse", "ambient_occlusion"]


def _bake_via_labs(
    hou,
    objects: List[str],
    output_path: str,
    resolution: List[int],
    map_types: List[str],
    uv_layer: str,
    file_format: str,
) -> dict:
    """Bake multi-map via Labs Maps Baker."""
    parent = hou.node("/out")
    if parent is None:
        return skill_error("No /out context", "Cannot create bake nodes")

    baker = parent.createNode("maps_baker", "_tmp_bake_maps_labs")
    try:
        obj_str = " ".join(objects)
        set_parm_if_exists(baker, "soppath", obj_str) or set_parm_if_exists(baker, "objects", obj_str)
        set_parm_if_exists(baker, "picture", output_path)
        set_parm_if_exists(baker, "resolution", resolution)
        if uv_layer != "uv":
            set_parm_if_exists(baker, "uvlayer", uv_layer) or set_parm_if_exists(baker, "uv_layer", uv_layer)
        set_parm_if_exists(baker, "file_format", file_format)

        # Enable requested map types on the baker
        _toggle_labs_maps(baker, map_types)

        try:
            baker.render(verbose=False)
        except TypeError:
            baker.render()

        written = [
            f for f in _generate_expected_files(objects, output_path, map_types, file_format) if os.path.isfile(f)
        ]

        return skill_success(
            "Baked {} map type(s) via Labs Maps Baker".format(len(map_types)),
            bake_method="labs_maps_baker",
            written_files=written,
            output_path=output_path,
            resolution=resolution,
            map_types=map_types,
            objects=objects,
            prompt="Use list_bake_targets to verify UVs before baking, or transfer_maps for high-to-low transfer.",
        )
    finally:
        try:
            baker.destroy()
        except Exception:
            pass


def _toggle_labs_maps(baker, map_types: List[str]) -> None:
    """Toggle the Labs Maps Baker parameters for each requested map type."""
    param_map = {
        "normals": ("normal", "normals", "bake_normals"),
        "cavity": ("cavity", "cavitymap"),
        "curvature": ("curvature", "bake_curvature"),
        "diffuse": ("diffuse", "basecolor", "bake_diffuse", "bake_basecolor"),
        "roughness": ("roughness", "bake_roughness"),
        "metallic": ("metallic", "bake_metallic"),
        "thickness": ("thickness", "bake_thickness"),
        "world_position": ("worldpos", "world_position", "pworld"),
        "opacity": ("opacity", "bake_opacity"),
        "ambient_occlusion": ("ao", "ambientocclusion", "ambient_occlusion", "bake_ao"),
        "displacement": ("displacement", "bake_displacement"),
        "height": ("height", "bake_height"),
        "emission": ("emission", "emit", "bake_emission"),
        "scattering": ("scattering", "bake_scattering"),
        "transmission": ("transmission", "bake_transmission"),
        "basecolor": ("basecolor", "base_color", "diffuse"),
        "specular": ("specular", "bake_specular"),
        "subsurface": ("subsurface", "bake_subsurface"),
        "anisotropy": ("anisotropy", "anisotropic", "bake_anisotropy"),
        "coat": ("coat", "bake_coat"),
        "sheen": ("sheen", "bake_sheen"),
    }

    for mt in map_types:
        candidates = param_map.get(mt, (mt,))
        for cand in candidates:
            if set_parm_if_exists(baker, cand, True):
                break


def _generate_expected_files(objects: List[str], output_base: str, map_types: List[str], file_format: str) -> List[str]:
    """Generate expected output file paths based on Labs Maps Baker naming."""
    base_no_ext = os.path.splitext(output_base)[0]
    files = []
    for obj in objects:
        safe = obj.rsplit("/", 1)[-1]
        for mt in map_types:
            files.append("{}_{}_{}.{}".format(base_no_ext, safe, mt, file_format))
    return files


def _bake_via_rop(
    hou,
    objects: List[str],
    rop_path: str,
    output_path: str,
    resolution: List[int],
    map_types: List[str],
    uv_layer: str,
    file_format: str,
) -> dict:
    """Bake multi-map via Bake Texture ROP (one ROP per map type)."""
    written = []
    obj_str = " ".join(objects)

    for mt in map_types:
        rop = create_or_get_bake_rop(hou, rop_path)
        mt_output = _map_type_output(output_path, mt, file_format)
        set_parm_if_exists(rop, "soppath", obj_str) or set_parm_if_exists(rop, "objects", obj_str)
        set_parm_if_exists(rop, "picture", mt_output)
        set_parm_if_exists(rop, "resolution", resolution)
        if uv_layer != "uv":
            set_parm_if_exists(rop, "uvlayer", uv_layer) or set_parm_if_exists(rop, "uv_layer", uv_layer)

        _toggle_rop_maps(rop, mt)

        try:
            rop.render(verbose=False)
        except TypeError:
            rop.render()

        if os.path.isfile(mt_output):
            written.append(mt_output)

    return skill_success(
        "Baked {} map type(s) via Bake Texture ROP".format(len(map_types)),
        bake_method="bake_texture_rop",
        written_files=written,
        output_path=output_path,
        resolution=resolution,
        map_types=map_types,
        objects=objects,
        rop_path=rop_path,
    )


def _map_type_output(output_path: str, map_type: str, file_format: str) -> str:
    """Generate a per-map-type output path."""
    base, ext = os.path.splitext(output_path)
    if not ext:
        ext = "." + file_format
    return "{}_{}{}".format(base, map_type, ext)


def _toggle_rop_maps(rop, map_type: str) -> None:
    """Toggle Bake Texture ROP parameters for a given map type."""
    param_map = {
        "normals": ("normal", "normals", "bakeNormalMap"),
        "cavity": ("cavity", "cavitymap"),
        "curvature": ("curvature", "bakeCurvature"),
        "diffuse": ("diffuse", "basecolor"),
        "ambient_occlusion": ("ao", "ambient_occlusion", "bakeAmbientOcclusion"),
        "roughness": ("roughness", "bakeRoughness"),
        "metallic": ("metallic", "bakeMetallic"),
        "opacity": ("opacity", "bakeOpacity"),
        "thickness": ("thickness", "bakeThickness"),
        "displacement": ("displacement", "bakeDisplacement"),
    }

    candidates = param_map.get(map_type, (map_type,))
    for cand in candidates:
        if set_parm_if_exists(rop, cand, True):
            return


def bake_textures(
    rop_path: str,
    objects: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    resolution: Optional[List[int]] = None,
    map_types: Optional[List[str]] = None,
    uv_layer: str = "uv",
    file_format: str = "exr",
) -> dict:
    """Bake multiple texture maps from geometry to image files."""
    types = map_types or list(_DEFAULT_MAP_TYPES)
    valid, invalid = validate_map_types(types)
    if invalid:
        return skill_error(
            "Invalid map types: {}".format(invalid),
            "Supported types: {}".format(sorted(set(types))),
        )
    if not valid:
        return skill_error("No valid map types provided", "Provide at least one valid map type")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        methods = detect_bake_methods(hou)
        geo = collect_geometry(hou, objects)

        if not geo:
            return skill_error(
                "No geometry found",
                "Provide 'objects' or ensure renderable OBJ nodes exist",
            )

        res = resolution or [1024, 1024]
        out = output_path or "$HIP/bake.$F4.exr"

        if methods["labs_maps_baker_available"]:
            return _bake_via_labs(hou, geo, out, res, valid, uv_layer, file_format)

        if methods["bake_texture_rop_available"]:
            return _bake_via_rop(hou, geo, rop_path, out, res, valid, uv_layer, file_format)

        return skill_error(
            "No bake method available",
            "Install sidefx_labs for Labs Maps Baker or use Houdini 20+ for Bake Texture ROP",
            available_methods=methods["available_methods"],
            recommendations=methods["recommendations"],
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to bake textures")


@skill_entry
def main(**kwargs) -> dict:
    return bake_textures(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
