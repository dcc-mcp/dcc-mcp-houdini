"""Build a deterministic Copernicus -> Unreal PBR texture-set manifest.

This skill assembles a sidecar manifest from Copernicus (COP) output nodes or
explicit source files. It does not render or cook: the COP outputs are produced
with ``houdini_render__render_rop`` and verified with
``houdini_copernicus__inspect_cop_output`` first. The manifest records the
color-space, naming and /Game destination conventions and carries ready-to-call
``unreal_assets__import_asset`` / ``unreal_assets__create_texture_material``
plans so a downstream Unreal session can consume it without re-deriving them.
"""

import glob
import os
from typing import Any, Dict, List, Optional

import _unreal_common as common
from dcc_mcp_core.skill import run_main, skill_entry, skill_error, skill_exception, skill_success

# Candidate output parameters on a Copernicus output (ROP image) node, in probe
# order. Node types differ in which one they expose, so a miss is not fatal.
_OUTPUT_PARMS = ("copoutput", "copfile", "filename", "output", "picture", "vm_picture")
_MAX_MATCHES = 64

# Bound the whole declaration so a stray agent request cannot explode I/O.
_MAX_MAPS = 32


def _import_hou():
    """Lazy import: hou exists only inside a Houdini interpreter."""
    try:
        import hou

        return hou
    except ImportError:
        return None


def _expand(hou, path):
    if hou is None:
        return path
    expand = getattr(hou, "expandString", None)
    if callable(expand):
        try:
            return expand(path)
        except Exception:  # noqa: BLE001 - fall back to the literal path
            return path
    return path


def _match_paths(expanded):
    """Resolve frame/UDIM glob tokens to concrete files when present."""
    if any(token in expanded for token in ("*", "?", "[")):
        return sorted(glob.glob(expanded))[:_MAX_MATCHES]
    return [expanded] if expanded else []


def _resolve_cop_output(hou, node_path):
    node = hou.node(node_path)
    if node is None:
        raise ValueError("COP output node not found: {}".format(node_path))
    for name in _OUTPUT_PARMS:
        parm = node.parm(name) if hasattr(node, "parm") else None
        if parm is None:
            continue
        try:
            value = parm.eval()
        except Exception:  # noqa: BLE001 - try the next candidate parameter
            continue
        if isinstance(value, str) and value:
            expanded = _expand(hou, value)
            matches = _match_paths(expanded)
            return matches[0] if matches else expanded, name
    return None, None


def export_copernicus_for_unreal(
    maps: List[Dict[str, Any]],
    asset_name: str,
    output_path: str,
    destination_path: Optional[str] = None,
    material_name: Optional[str] = None,
    material_destination_path: Optional[str] = None,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Assemble a texture-set manifest from Copernicus outputs.

    Args:
        maps: Non-empty list of map declarations. Each item needs ``map_type``
            (one of the canonical PBR types) plus either ``node_path`` (a COP
            output node whose output file is probed) or ``source_path`` (an
            explicit file). Optional per-map ``channel_packing`` and ``udim``.
        asset_name: Base asset name, e.g. ``Rock_Cliff``.
        output_path: Where the sidecar manifest JSON is written. Houdini
            variable tokens (e.g. ``$HIP``) are expanded when running inside a
            Houdini session.
        destination_path: Unreal Content Browser folder for textures.
        material_name: Name of the material asset to create.
        material_destination_path: Content Browser folder for the material.
        overwrite: Allow replacing an existing manifest at ``output_path``.
    """
    if not isinstance(maps, list) or not maps:
        return skill_error("No maps declared", "maps must be a non-empty list of map declarations")
    if len(maps) > _MAX_MAPS:
        return skill_error("Too many maps", "at most {} maps are supported".format(_MAX_MAPS))
    try:
        common.validate_identifier(asset_name, "asset_name")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("output_path must be a non-empty string")
        dest = destination_path or "/Game/Textures/{}".format(asset_name)
        common.validate_game_path(dest, "destination_path")
        mat_dest = material_destination_path or "/Game/Materials"
        common.validate_game_path(mat_dest, "material_destination_path")
        mat_name = material_name or "M_{}".format(asset_name)
        common.validate_identifier(mat_name, "material_name")
    except (ValueError, TypeError) as exc:
        return skill_error("Invalid export configuration", str(exc))

    # hou is needed for node_path resolution AND for expanding Houdini variable
    # tokens (e.g. $HIP) in output_path / source_path. A source_path-only request
    # with a "$" token must still load hou so the token is expanded inside a
    # Houdini session. Outside Houdini _import_hou() returns None and _expand()
    # keeps the literal path, with an explicit warning recorded in the manifest.
    needs_node_resolution = any(
        isinstance(item, dict) and item.get("node_path") and not item.get("source_path") for item in maps
    )
    has_dollar_token = "$" in output_path or any(
        isinstance(item, dict) and isinstance(item.get("source_path"), str) and "$" in item["source_path"]
        for item in maps
    )
    hou = _import_hou() if (needs_node_resolution or has_dollar_token) else None

    try:
        resolved_output = _expand(hou, output_path) if "$" in output_path else output_path
        textures: List[Dict[str, Any]] = []
        seen = set()
        for index, item in enumerate(maps):
            if not isinstance(item, dict):
                raise ValueError("maps[{}] must be an object".format(index))
            map_type = item.get("map_type")
            if map_type not in common.MAP_TYPES:
                raise ValueError(
                    "maps[{}].map_type must be one of {}, got {!r}".format(index, sorted(common.MAP_TYPES), map_type)
                )
            if map_type in seen:
                raise ValueError("duplicate map_type: {}".format(map_type))
            seen.add(map_type)

            packing = common.normalize_channel_packing(
                item.get("channel_packing"), common.MAP_TYPES[map_type]["channel_packing"]
            )
            udim = common.normalize_udim(item.get("udim"))

            source_path = item.get("source_path")
            node_path = item.get("node_path")
            resolved = None
            if source_path:
                if not isinstance(source_path, str):
                    raise ValueError("maps[{}].source_path must be a string".format(index))
                resolved = _expand(hou, source_path) if "$" in source_path else source_path
            elif node_path:
                if hou is None:
                    return skill_error(
                        "Houdini not available",
                        "hou is required to resolve node_path; provide source_path instead or run inside Houdini",
                    )
                if not isinstance(node_path, str):
                    raise ValueError("maps[{}].node_path must be a string".format(index))
                resolved, _parm_name = _resolve_cop_output(hou, node_path)
                if resolved is None:
                    raise ValueError(
                        "could not resolve an output file from COP node {} (no known output parameter)".format(
                            node_path
                        )
                    )
            else:
                raise ValueError("maps[{}] needs either source_path or node_path".format(index))

            textures.append(
                {
                    "map_type": map_type,
                    "source_path": resolved,
                    "node_path": node_path if node_path else None,
                    "artifact_exists": os.path.isfile(resolved),
                    "channel_packing": packing,
                    "udim": udim,
                }
            )

        manifest = common.build_manifest(asset_name, dest, mat_name, mat_dest, textures)
        if "$" in resolved_output:
            manifest["warnings"].append(
                "output_path still contains an unexpanded '$' token (e.g. $HIP); Houdini "
                "variable expansion was unavailable (no Houdini session), so the manifest "
                "was written to the literal path: {}".format(resolved_output)
            )
        common.write_manifest(resolved_output, manifest, overwrite=overwrite)
        return skill_success(
            "Built Copernicus -> Unreal texture-set manifest",
            manifest_path=resolved_output,
            manifest=manifest,
            texture_count=len(textures),
            import_call_count=len(manifest["import_plan"]),
            has_material_plan=manifest["material_plan"] is not None,
            artifacts_present=sum(1 for tex in textures if tex["artifact_exists"]),
            warnings=manifest["warnings"],
        )
    except (ValueError, TypeError, OSError) as exc:
        return skill_exception(exc, message="Failed to build Copernicus -> Unreal manifest", include_traceback=False)


@skill_entry
def main(**kwargs):
    return export_copernicus_for_unreal(**kwargs)


if __name__ == "__main__":
    run_main(main)
