"""Configure a bake output for UDIM tiles so a multi-tile bake cannot collapse into one file."""

from __future__ import annotations

from typing import Any

from _texture_bake_common import (
    UDIM_TOKEN,
    bake_output_paths,
    create_or_get_bake_rop,
    detect_bake_methods,
    set_parm_if_exists,
    udim_info,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

OUTPUT_PATH_PARMS = ("copoutput", "output", "vm_picture", "filename", "picture")

# Defaults this tool tries to seed. Bake writers differ in which parameters they
# expose, so a default that cannot be applied is reported, not silently dropped.
BAKE_RANGE_PARMS = ("bake_range", "trange")


def _resolve_tiles(hou: Any, target_path: str, tile_range) -> tuple:
    """Return (tiles, source) where source explains where the tiles came from."""
    if tile_range is not None:
        if not isinstance(tile_range, (list, tuple)) or not tile_range:
            raise ValueError("tile_range must be a non-empty list of tile indices")
        tiles = []
        for tile in tile_range:
            if not isinstance(tile, int) or isinstance(tile, bool):
                raise ValueError("tile_range entries must be integers")
            if tile not in tiles:
                tiles.append(tile)
        return sorted(tiles), "tile_range"
    if target_path is None:
        raise ValueError("target_path or tile_range is required")
    info = udim_info(hou, target_path)
    if info["udim_detection"] != "computed":
        return [], info["udim_detection"]
    return info["udim_tiles"], "geometry"


def configure_udim_bake(
    rop_path: str,
    target_path: str = None,
    output_path: str = None,
    tile_range=None,
    parameters: dict = None,
) -> dict:
    try:
        import hou
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        if not isinstance(rop_path, str) or not rop_path.startswith("/"):
            raise ValueError("rop_path must be an absolute path")
        if output_path is not None and not isinstance(output_path, str):
            raise ValueError("output_path must be a string")
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        methods = detect_bake_methods(hou)
        if not methods.get("available_methods"):
            return skill_error(
                "No bake method available",
                "No Labs Maps Baker or Bake Texture ROP was detected",
                available_methods=[],
                recommendations=methods.get("recommendations", []),
            )
        tiles, source = _resolve_tiles(hou, target_path, tile_range)
        if not tiles:
            return skill_error(
                "No UDIM tiles resolved",
                "Could not determine the tile set; udim_detection={}".format(source),
                rop_path=rop_path,
                target_path=target_path,
                udim_detection=source,
                needs_udim_output=False,
            )
        rop = create_or_get_bake_rop(hou, rop_path)
        # Caller overrides are strict: an unknown name fails the call.
        for name, value in (parameters or {}).items():
            if not set_parm_if_exists(rop, name, value):
                raise ValueError("Parameter not found: {}".format(name))

        resolved_output = output_path
        unapplied_defaults = []
        if output_path:
            if UDIM_TOKEN in output_path:
                resolved_output = output_path
            elif len(tiles) > 1:
                root, dot, extension = output_path.rpartition(".")
                resolved_output = (root if dot else output_path) + "." + UDIM_TOKEN + (dot + extension if dot else "")
            else:
                resolved_output = output_path
            if not any(set_parm_if_exists(rop, name, resolved_output) for name in OUTPUT_PATH_PARMS):
                unapplied_defaults.append("output_path")
            if len(tiles) > 1 and not any(set_parm_if_exists(rop, name, 1) for name in BAKE_RANGE_PARMS):
                unapplied_defaults.append("bake_range")

        paths = bake_output_paths(resolved_output, tiles) if resolved_output else []
        return skill_success(
            "Configured UDIM bake",
            rop_path=rop.path(),
            target_path=target_path,
            tile_count=len(tiles),
            udim_tiles=tiles,
            tile_source=source,
            needs_udim_output=len(tiles) > 1,
            output_path=resolved_output,
            output_paths=paths,
            unapplied_defaults=unapplied_defaults,
            available_methods=methods.get("available_methods", []),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure UDIM bake")


@skill_entry
def main(**kwargs):
    return configure_udim_bake(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
