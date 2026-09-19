"""Configure a bake output for UDIM tiles so a multi-tile bake cannot collapse into one file."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from _texture_bake_common import (
    UDIM_TOKEN,
    bake_output_paths,
    create_or_get_bake_rop_ex,
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


def _resolved_output(output_path: str, tiles) -> str:
    if not output_path or UDIM_TOKEN in output_path:
        return output_path
    if len(tiles) <= 1:
        return output_path
    root, dot, extension = output_path.rpartition(".")
    return (root if dot else output_path) + "." + UDIM_TOKEN + (dot + extension if dot else "")


def _parm_exists(rop: Any, name: str, value: Any) -> bool:
    """True when *rop* exposes *name* as a parm of the shape *value* needs."""
    if isinstance(value, (list, tuple)):
        return rop.parmTuple(name) is not None
    return rop.parm(name) is not None


def _first_existing(rop: Any, names: Tuple[str, ...]) -> Optional[str]:
    """First name in *names* that *rop* exposes, or None."""
    for name in names:
        if rop.parm(name) is not None:
            return name
    return None


def _parm_value(rop: Any, name: str, value: Any) -> Any:
    """Current value of *name*, so a failed write can put it back."""
    if isinstance(value, (list, tuple)):
        return tuple(rop.parmTuple(name).eval())
    return rop.parm(name).eval()


def _restore_parms(rop: Any, entries) -> List[str]:
    """Restore every snapshotted parm; return the names that could not be.

    Keeps going after a failure so one stubborn parm does not leave the others
    half-restored.
    """
    unrestored = []
    for name, value, original in entries:
        try:
            if isinstance(value, (list, tuple)):
                rop.parmTuple(name).set(original)
            else:
                rop.parm(name).set(original)
        except Exception:
            unrestored.append(name)
    return unrestored


def _plan_writes(rop: Any, overrides: dict, resolved_output: str, tiles) -> Tuple[list, List[str]]:
    """Resolve the writes this request will make, before making any of them.

    Returns ``(planned, skipped_parameters)``. Caller overrides come first and
    are strict; the seeded defaults only take the first parm the ROP actually
    exposes, and a default with no home is reported instead of failing.
    """
    planned = list(overrides.items())
    skipped = []
    if resolved_output:
        output_parm = _first_existing(rop, OUTPUT_PATH_PARMS)
        if output_parm is None:
            skipped.append("output_path")
        else:
            planned.append((output_parm, resolved_output))
        if len(tiles) > 1:
            range_parm = _first_existing(rop, BAKE_RANGE_PARMS)
            if range_parm is None:
                skipped.append("bake_range")
            else:
                planned.append((range_parm, 1))
    return planned, skipped


def _apply_writes(rop: Any, planned) -> None:
    """Write every planned parm as one transaction.

    Every name is validated before anything is written, so an unknown caller
    name fails the call without touching the ROP. Each parm's previous value is
    snapshotted first, so a setter that raises part-way leaves a pre-existing
    ROP exactly as it was found instead of half-configured.
    """
    missing = [str(name) for name, value in planned if not _parm_exists(rop, name, value)]
    if missing:
        raise ValueError("Parameter not found: {}".format(", ".join(sorted(missing))))

    entries = [(name, value, _parm_value(rop, name, value)) for name, value in planned]
    try:
        for name, value, _original in entries:
            set_parm_if_exists(rop, name, value)
    except BaseException as exc:
        unrestored = _restore_parms(rop, entries)
        if unrestored:
            raise ValueError(
                "Failed to configure UDIM bake ({}) and could not roll back: {}".format(
                    exc, ", ".join(sorted(str(name) for name in unrestored))
                )
            ) from exc
        raise


def _apply(rop: Any, tiles, source: str, target_path: str, output_path: str, overrides: dict, methods: dict) -> dict:
    """Apply the resolved configuration.

    Runs inside the caller's rollback: any exception propagates so a ROP this
    request created is destroyed. A pre-existing ROP is not destroyed, so the
    parm writes here are their own transaction and are rolled back to the values
    they had on entry.
    """
    resolved_output = _resolved_output(output_path, tiles)
    planned, skipped_parameters = _plan_writes(rop, overrides, resolved_output, tiles)
    _apply_writes(rop, planned)

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
        skipped_parameters=skipped_parameters,
        available_methods=methods.get("available_methods", []),
    )


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
        for name in parameters or {}:
            if not isinstance(name, str):
                raise ValueError("parameter names must be strings")
        methods = detect_bake_methods(hou)
        if not methods.get("available_methods"):
            return skill_error(
                "No bake method available",
                "No Labs Maps Baker or Bake Texture ROP was detected",
                available_methods=[],
                recommendations=methods.get("recommendations", []),
            )
        # Resolve everything that can fail before the ROP exists, so a failed
        # request has nothing to clean up.
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
        rop, created_rop = create_or_get_bake_rop_ex(hou, rop_path)
        try:
            return _apply(rop, tiles, source, target_path, output_path, dict(parameters or {}), methods)
        except BaseException:
            if created_rop:
                try:
                    rop.destroy()
                except Exception:
                    pass
            raise
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure UDIM bake")


@skill_entry
def main(**kwargs):
    return configure_udim_bake(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
