"""Houdini-independent core for the Copernicus -> Unreal texture-set manifest.

This module is pure stdlib Python: it has no ``hou`` import, no USD/pxr
dependency, and no filesystem side effects beyond the explicit manifest
read/write helpers. Keeping the contract builder here makes the color and
naming conventions unit-testable without a Houdini install and keeps every
shipped source Python 3.7-parseable.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

SCHEMA_VERSION = "1.0"

# Canonical PBR map catalog.
#   * ``color_space``  - "srgb" for color maps, "linear" for data maps.
#   * ``material_param`` - the dcc-mcp-unreal ``create_texture_material``
#     argument the map feeds, or None when the map is imported but not wired
#     into the generated material.
#   * ``channel_packing`` - default descriptive packing recorded in the manifest.
# Only ``base_color`` and ``emissive`` are sRGB; everything else is linear
# (non_color_texture=True), matching import_asset's data-texture flag contract.
MAP_TYPES = {
    "base_color": {"color_space": "srgb", "material_param": "texture_path", "channel_packing": "rgb"},
    "normal": {"color_space": "linear", "material_param": "normal_texture_path", "channel_packing": "rgb"},
    "roughness": {"color_space": "linear", "material_param": "roughness_texture_path", "channel_packing": "r"},
    "metallic": {"color_space": "linear", "material_param": "metallic_texture_path", "channel_packing": "r"},
    "ambient_occlusion": {
        "color_space": "linear",
        "material_param": "ambient_occlusion_texture_path",
        "channel_packing": "r",
    },
    "emissive": {"color_space": "srgb", "material_param": None, "channel_packing": "rgb"},
    "opacity": {"color_space": "linear", "material_param": None, "channel_packing": "r"},
    "height": {"color_space": "linear", "material_param": None, "channel_packing": "r"},
    "displacement": {"color_space": "linear", "material_param": None, "channel_packing": "r"},
    "specular": {"color_space": "linear", "material_param": None, "channel_packing": "r"},
}

CHANNEL_PACKING = frozenset({"rgb", "rgba", "r", "orm", "grayscale"})

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_GAME_PATH_RE = re.compile(r"^/Game(?:/[A-Za-z0-9_]+)*$")

# Engine-side capabilities intentionally out of scope for v1. They are recorded
# as metadata/notes but never acted upon, so the manifest never overclaims.
DEFERRED_CAPABILITIES = (
    "OCIO/ACES color configuration",
    "ORM channel packing (recorded, not split)",
    "UDIM / virtual texturing (metadata only)",
    "Lumen / Nanite engine-side features",
)


def validate_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        raise ValueError("{} must match [A-Za-z0-9_]+, got {!r}".format(label, value))
    return value


def validate_game_path(value: Any, label: str = "destination_path") -> str:
    if not isinstance(value, str) or not _GAME_PATH_RE.match(value):
        raise ValueError("{} must be a /Game/... path, got {!r}".format(label, value))
    return value


def normalize_channel_packing(value: Any, default: str) -> str:
    chosen = default if value is None else value
    if chosen not in CHANNEL_PACKING:
        raise ValueError("channel_packing must be one of {}, got {!r}".format(sorted(CHANNEL_PACKING), chosen))
    return chosen


def normalize_udim(value: Any) -> Dict[str, Any]:
    """Return a bounded, JSON-safe UDIM descriptor (feature itself is deferred)."""
    if value is None or value is False:
        return {"enabled": False, "tiles": [], "pattern": "", "deferred": True}
    if value is True:
        return {"enabled": True, "tiles": [], "pattern": "", "deferred": True}
    if isinstance(value, dict):
        tiles = value.get("tiles", [])
        if not isinstance(tiles, list):
            raise ValueError("udim.tiles must be a list")
        pattern = value.get("pattern", "")
        if not isinstance(pattern, str):
            raise ValueError("udim.pattern must be a string")
        return {
            "enabled": bool(value.get("enabled", True)),
            "tiles": [str(tile) for tile in tiles[:64]],
            "pattern": pattern[:256],
            "deferred": True,
        }
    raise ValueError("udim must be a boolean or an object")


def color_fields(map_type: str) -> Dict[str, Any]:
    srgb = MAP_TYPES[map_type]["color_space"] == "srgb"
    return {
        "color_space": "srgb" if srgb else "linear",
        "srgb": srgb,
        "source_color_space": "srgb" if srgb else "",
        "non_color_texture": not srgb,
    }


def _suffix(map_type: str) -> str:
    return "".join(part.capitalize() for part in map_type.split("_"))


def build_manifest(
    asset_name: str,
    destination_path: str,
    material_name: str,
    material_destination_path: str,
    textures: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a deterministic manifest from already-resolved texture entries.

    Each entry in ``textures`` must contain ``map_type``, ``source_path``,
    ``node_path`` (or None), ``artifact_exists``, ``channel_packing`` and
    ``udim``.
    """
    import_plan = []
    textures_out = []
    material_args: Dict[str, Any] = {}
    warnings: List[str] = []
    seen = set()

    for tex in textures:
        map_type = tex["map_type"]
        if map_type in seen:
            raise ValueError("duplicate map_type: {}".format(map_type))
        seen.add(map_type)
        spec = MAP_TYPES[map_type]
        fields = color_fields(map_type)
        texture_asset_name = "T_{}_{}".format(asset_name, _suffix(map_type))
        object_path = "{}/{}".format(destination_path, texture_asset_name)
        source_path = tex["source_path"]
        exists = bool(tex.get("artifact_exists"))

        if not exists:
            warnings.append(
                "artifact not found on disk (render the COP output with houdini-render first): {}".format(source_path)
            )
        if tex["channel_packing"] == "orm":
            warnings.append("ORM channel packing for '{}' recorded but not split (deferred)".format(map_type))
        if tex["udim"].get("enabled"):
            warnings.append("UDIM for '{}' recorded as metadata; virtual texturing deferred".format(map_type))

        import_plan.append(
            {
                "tool": "unreal_assets__import_asset",
                "arguments": {
                    "source_path": source_path,
                    "destination_path": destination_path,
                    "asset_name": texture_asset_name,
                    "source_color_space": fields["source_color_space"],
                    "non_color_texture": fields["non_color_texture"],
                },
            }
        )
        textures_out.append(
            {
                "map_type": map_type,
                "asset_name": texture_asset_name,
                "object_path": object_path,
                "source_path": source_path,
                "node_path": tex.get("node_path"),
                "artifact_exists": exists,
                "color_space": fields["color_space"],
                "srgb": fields["srgb"],
                "source_color_space": fields["source_color_space"],
                "non_color_texture": fields["non_color_texture"],
                "channel_packing": tex["channel_packing"],
                "udim": tex["udim"],
            }
        )
        material_param = spec["material_param"]
        if material_param:
            material_args[material_param] = object_path

    material_plan = None
    if "texture_path" in material_args:
        material_args["material_name"] = material_name
        material_args["destination_path"] = material_destination_path
        material_plan = {"tool": "unreal_assets__create_texture_material", "arguments": material_args}
    else:
        warnings.append("no base_color map; create_texture_material plan omitted (base color is required)")

    return {
        "schema_version": SCHEMA_VERSION,
        "asset_name": asset_name,
        "color_convention": "base_color and emissive are sRGB; all other maps are linear (non_color_texture=True)",
        "destination_path": destination_path,
        "material": {"name": material_name, "destination_path": material_destination_path},
        "textures": textures_out,
        "import_plan": import_plan,
        "material_plan": material_plan,
        "warnings": warnings,
        "deferred": list(DEFERRED_CAPABILITIES),
        "note": (
            "Deterministic sidecar manifest. Render Copernicus outputs with houdini-render first; "
            "unreal_assets__import_asset consumes each textures[].source_path and "
            "unreal_assets__create_texture_material consumes material_plan."
        ),
    }


def write_manifest(path: str, manifest: Dict[str, Any], overwrite: bool = True) -> None:
    if os.path.exists(path) and not overwrite:
        raise FileExistsError("manifest already exists (overwrite=False): {}".format(path))
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, sort_keys=True, indent=2)
        handle.write("\n")


def load_manifest(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_manifest(data: Any) -> bool:
    """Validate schema and re-derive the color convention for every texture."""
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version: {!r}".format(data.get("schema_version")))
    for key in ("textures", "import_plan", "warnings", "destination_path", "asset_name"):
        if key not in data:
            raise ValueError("manifest missing key: {}".format(key))
    textures = data["textures"]
    if not isinstance(textures, list) or not textures:
        raise ValueError("manifest.textures must be a non-empty list")
    required = (
        "asset_name",
        "object_path",
        "source_path",
        "color_space",
        "srgb",
        "non_color_texture",
        "channel_packing",
    )
    for index, tex in enumerate(textures):
        if not isinstance(tex, dict):
            raise ValueError("textures[{}] must be an object".format(index))
        map_type = tex.get("map_type")
        if map_type not in MAP_TYPES:
            raise ValueError("textures[{}].map_type unknown: {!r}".format(index, map_type))
        for key in required:
            if key not in tex:
                raise ValueError("textures[{}] missing key: {}".format(index, key))
        fields = color_fields(map_type)
        if (
            tex.get("color_space") != fields["color_space"]
            or tex.get("srgb") != fields["srgb"]
            or tex.get("non_color_texture") != fields["non_color_texture"]
        ):
            raise ValueError("textures[{}] violates the color convention for {}".format(index, map_type))
    return True
