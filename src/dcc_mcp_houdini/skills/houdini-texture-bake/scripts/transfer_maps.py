"""Transfer maps from high-res source to low-res target via Labs Maps Baker or raytrace/cage fallback."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _texture_bake_common import (  # noqa: E402
    check_uvs,
    detect_bake_methods,
    set_parm_if_exists,
    validate_map_types,
)

_VALID_TRANSFER_MODES = ("raytrace", "cage", "projection")
_DEFAULT_TRANSFER_MAP_TYPES = ["normals"]


def _transfer_via_labs(
    hou,
    source: str,
    target: str,
    map_types: List[str],
    output_dir: str,
    resolution: List[int],
    file_format: str,
    transfer_mode: str,
    search_distance: float,
) -> dict:
    """Transfer maps using Labs Maps Baker with high-res source input."""
    parent = hou.node("/out")
    if parent is None:
        return skill_error("No /out context", "Cannot create bake nodes")

    baker = parent.createNode("maps_baker", "_tmp_transfer_labs")
    try:
        set_parm_if_exists(baker, "soppath", target)
        set_parm_if_exists(baker, "highres", source)
        set_parm_if_exists(baker, "highresobj", source)
        set_parm_if_exists(baker, "resolution", resolution)
        set_parm_if_exists(baker, "file_format", file_format)
        if transfer_mode == "cage":
            set_parm_if_exists(baker, "usecagemesh", True)
            set_parm_if_exists(baker, "cagemesh", source)
        elif transfer_mode == "raytrace":
            set_parm_if_exists(baker, "searchdist", search_distance)

        # Enable requested map types
        _toggle_transfer_maps(baker, map_types)

        baked_files = []
        for mt in map_types:
            out_file = os.path.join(
                output_dir,
                "{}_from_{}_{}.{}".format(
                    target.rsplit("/", 1)[-1],
                    source.rsplit("/", 1)[-1],
                    mt,
                    file_format,
                ),
            )
            set_parm_if_exists(baker, "picture", out_file)

            try:
                baker.render(verbose=False)
            except TypeError:
                baker.render()

            if os.path.isfile(out_file):
                baked_files.append(out_file)

        return skill_success(
            "Transferred {} map(s) via Labs Maps Baker".format(len(baked_files)),
            bake_method="labs_maps_baker",
            transfer_mode=transfer_mode,
            written_files=baked_files,
            source=source,
            target=target,
            resolution=resolution,
            map_types=map_types,
            prompt="Check output_dir for baked maps. Use bake_textures for additional map types.",
        )
    finally:
        try:
            baker.destroy()
        except Exception:
            pass


def _toggle_transfer_maps(baker, map_types: List[str]) -> None:
    """Toggle Labs Maps Baker parameters for transfer-relevant map types."""
    param_map = {
        "normals": ("normal", "normals", "bake_normals"),
        "displacement": ("displacement", "bake_displacement", "height"),
        "diffuse": ("diffuse", "basecolor", "bake_diffuse"),
        "ambient_occlusion": ("ao", "ambientocclusion", "bake_ao"),
    }
    for mt in map_types:
        candidates = param_map.get(mt, (mt,))
        for cand in candidates:
            if set_parm_if_exists(baker, cand, True):
                break


def _transfer_via_rop(
    hou,
    source: str,
    target: str,
    map_types: List[str],
    output_dir: str,
    resolution: List[int],
    file_format: str,
    transfer_mode: str,
    search_distance: float,
) -> dict:
    """Transfer maps using Bake Texture ROP with high-res source plugged into second input."""
    parent = hou.node("/out")
    if parent is None:
        return skill_error("No /out context", "Cannot create bake nodes")

    baked_files = []

    for mt in map_types:
        for type_name in ("baker::2.0", "game_simple_baker", "bake_texture"):
            try:
                rop = parent.createNode(type_name, "_tmp_transfer_{}".format(mt))
                break
            except Exception:
                continue
        else:
            continue

        try:
            set_parm_if_exists(rop, "soppath", target)
            set_parm_if_exists(rop, "resolution", resolution)
            if transfer_mode == "raytrace":
                set_parm_if_exists(rop, "searchdist", search_distance)

            # Enable this specific map type
            mt_candidates = {
                "normals": ("normal", "normals", "bakeNormalMap"),
                "displacement": ("displacement", "bakeDisplacement"),
                "diffuse": ("diffuse", "basecolor"),
                "ambient_occlusion": ("ao", "ambient_occlusion", "bakeAmbientOcclusion"),
            }
            for cand in mt_candidates.get(mt, (mt,)):
                if set_parm_if_exists(rop, cand, True):
                    break

            out_file = os.path.join(
                output_dir,
                "{}_from_{}_{}.{}".format(
                    target.rsplit("/", 1)[-1],
                    source.rsplit("/", 1)[-1],
                    mt,
                    file_format,
                ),
            )
            set_parm_if_exists(rop, "picture", out_file)

            try:
                rop.render(verbose=False)
            except TypeError:
                rop.render()

            if os.path.isfile(out_file):
                baked_files.append(out_file)
        finally:
            try:
                rop.destroy()
            except Exception:
                pass

    return skill_success(
        "Transferred {} map(s) via Bake Texture ROP".format(len(baked_files)),
        bake_method="bake_texture_rop",
        transfer_mode=transfer_mode,
        written_files=baked_files,
        source=source,
        target=target,
        resolution=resolution,
        map_types=map_types,
    )


def transfer_maps(
    source: str,
    target: str,
    map_types: Optional[List[str]] = None,
    output_dir: str = "/tmp",
    resolution: Optional[List[int]] = None,
    file_format: str = "png",
    transfer_mode: str = "raytrace",
    search_distance: float = 0.1,
) -> dict:
    """Transfer texture maps from high-res source to low-res target."""
    if transfer_mode not in _VALID_TRANSFER_MODES:
        return skill_error(
            "Invalid transfer_mode: {}".format(transfer_mode),
            "Use one of: {}".format(", ".join(_VALID_TRANSFER_MODES)),
        )

    types = map_types or list(_DEFAULT_TRANSFER_MAP_TYPES)
    valid, invalid = validate_map_types(types)
    if invalid:
        return skill_error(
            "Invalid map types: {}".format(invalid),
            "Supported types for transfer: normals, displacement, diffuse, ambient_occlusion",
        )
    if not valid:
        return skill_error("No valid map types", "Provide at least one valid map type")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        # Validate source and target exist
        for node_path in (source, target):
            if hou.node(node_path) is None:
                return skill_error(
                    "Node not found: {}".format(node_path),
                    "Verify the node path is correct",
                )

        # Check target has UVs
        target_uvs = check_uvs(hou, target)
        if not target_uvs:
            return skill_error(
                "Target has no UVs: {}".format(target),
                "Transfer target must have UV attributes. Run list_bake_targets() to find UV-equipped geometry.",
            )

        methods = detect_bake_methods(hou)
        res = resolution or [1024, 1024]

        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        if methods["labs_maps_baker_available"]:
            return _transfer_via_labs(
                hou,
                source,
                target,
                valid,
                output_dir,
                res,
                file_format,
                transfer_mode,
                search_distance,
            )

        if methods["bake_texture_rop_available"]:
            return _transfer_via_rop(
                hou,
                source,
                target,
                valid,
                output_dir,
                res,
                file_format,
                transfer_mode,
                search_distance,
            )

        return skill_error(
            "No bake method available for transfer",
            "Install sidefx_labs for Labs Maps Baker or use Houdini 20+ for Bake Texture ROP",
            available_methods=methods["available_methods"],
            recommendations=methods["recommendations"],
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to transfer maps")


@skill_entry
def main(**kwargs) -> dict:
    return transfer_maps(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
