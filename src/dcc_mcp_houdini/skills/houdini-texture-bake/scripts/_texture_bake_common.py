"""Shared helpers for Houdini texture-bake skills.

Detects available bake methods, creates ROPs, validates UVs, and provides
common utilities for all bake scripts.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional, Tuple

from dcc_mcp_houdini._domain_graph import (
    UV_NAME_PREFIX,
    cooked_geometry,
    udim_tiles,
    uv_attribute_names,
    uv_values,
)

# Output-path token the bake writers replace with the concrete UDIM tile.
UDIM_TOKEN = "%(UDIM)d"

# A single-tile bake needs no UDIM token in its output path.
UDIM_OUTPUT_THRESHOLD = 1

# Map-type vocabulary shared across bake_textures and transfer_maps.
# Labs Maps Baker supports ~20+ types; Bake Texture ROP supports a subset.
_MAP_TYPE_VOCABULARY = {
    "normals",
    "cavity",
    "curvature",
    "diffuse",
    "roughness",
    "metallic",
    "thickness",
    "world_position",
    "opacity",
    "ambient_occlusion",
    "displacement",
    "height",
    "emission",
    "scattering",
    "transmission",
    "basecolor",
    "specular",
    "subsurface",
    "anisotropy",
    "coat",
    "sheen",
}


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise ValueError."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def ensure_node(hou: Any, node_path: str, node_type: str, parent_path: str = "/out") -> Any:
    """Get or create a node at *node_path* with *node_type*."""
    node = hou.node(node_path)
    if node is not None:
        return node
    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError("Parent path not found: {}".format(parent_path))
    name = node_path.rsplit("/", 1)[-1]
    return parent.createNode(node_type, name)


def set_parm_if_exists(node: Any, name: str, value: Any) -> bool:
    """Set a scalar/tuple parm only when it exists. Return success."""
    if isinstance(value, (list, tuple)):
        parm_tuple = node.parmTuple(name)
        if parm_tuple is None:
            return False
        parm_tuple.set(tuple(value))
        return True
    parm = node.parm(name)
    if parm is None:
        return False
    parm.set(value)
    return True


def _detect_labs_maps_baker(hou: Any) -> bool:
    """Check whether the Labs Maps Baker node type is available."""
    try:
        node_type = hou.nodeType(hou.vopNodeTypeCategory(), "maps_baker")
        return node_type is not None
    except Exception:
        return False


def _detect_bake_texture_rop(hou: Any) -> bool:
    """Check whether the Bake Texture ROP (game_simple_baker / baker::2.0) is available."""
    for type_name in ("baker::2.0", "game_simple_baker", "bake_texture"):
        try:
            if hou.nodeType(hou.ropNodeTypeCategory(), type_name) is not None:
                return True
        except Exception:
            continue
    return False


def detect_bake_methods(hou: Any) -> dict:
    """Return available bake methods and their capabilities.

    Returns a dict with boolean flags and recommendations.
    """
    labs = _detect_labs_maps_baker(hou)
    rop = _detect_bake_texture_rop(hou)

    methods = []
    if labs:
        methods.append("labs_maps_baker")
    if rop:
        methods.append("bake_texture_rop")
    # COP is always available as a last resort
    methods.append("cop_fallback")

    return {
        "labs_maps_baker_available": labs,
        "bake_texture_rop_available": rop,
        "available_methods": methods,
        "recommended": "labs_maps_baker" if labs else ("bake_texture_rop" if rop else "cop_fallback"),
        "recommendations": ([] if labs else ["Install sidefx_labs for Labs Maps Baker (richest map-type support)."]),
    }


def validate_map_types(requested: List[str]) -> Tuple[List[str], List[str]]:
    """Split *requested* into (valid, invalid) using the shared vocabulary."""
    valid = [t for t in requested if t in _MAP_TYPE_VOCABULARY]
    invalid = [t for t in requested if t not in _MAP_TYPE_VOCABULARY]
    return valid, invalid


def collect_geometry(hou: Any, objects: Optional[List[str]] = None) -> List[str]:
    """Resolve object list; defaults to all renderable OBJ geometry."""
    if objects:
        return list(objects)

    obj_root = hou.node("/obj")
    if obj_root is None:
        return []

    geo_paths = []
    for child in obj_root.children():
        if hasattr(child, "displayNode") and child.displayNode() is not None:
            geo_paths.append(child.path())
    return geo_paths


def check_uvs(hou: Any, node_path: str) -> Optional[List[str]]:
    """Return UV attribute names on *node_path*'s display geometry, or None.

    When the node has no display geometry, returns None (not []).

    Shares the UV convention used by :func:`uv_attribute_names`: vertex
    attributes are reported before point attributes, and the name match is
    anchored at the start of the name so ``Cd_uv`` or ``flowuv`` are not taken
    for UV sets. Float attributes smaller than 2 components are skipped.
    """
    node = hou.node(node_path)
    if node is None:
        return None
    try:
        geo = node.displayNode().geometry() if hasattr(node, "displayNode") else None
    except Exception:
        return None
    if geo is None:
        return None

    uv_names = []
    for accessor in ("vertexAttribs", "pointAttribs"):
        method = getattr(geo, accessor, None)
        if not callable(method):
            continue
        for attr in method():
            try:
                data_type = attr.dataType()
                size = attr.size()
                name = attr.name()
            except Exception:
                continue
            if data_type != hou.attribData.Float or size < 2:
                continue
            if name.startswith(UV_NAME_PREFIX) and name not in uv_names:
                uv_names.append(name)
    return uv_names


def bake_geometry_info(hou: Any, node_path: str) -> Optional[dict]:
    """Return bake-relevant info dict for a single geometry node, or None."""
    node = hou.node(node_path)
    if node is None:
        return None
    display = node.displayNode() if hasattr(node, "displayNode") else None
    if display is None:
        info = {
            "path": node_path,
            "name": node.name(),
            "type": "obj",
            "has_display_geo": False,
            "geometry_available": False,
            "has_uvs": False,
            "uv_layers": [],
            "primitive_count": 0,
            "bake_ready": False,
        }
        info.update(udim_info(hou, node_path))
        return info

    # Resolve UDIM coverage *before* touching geometry: cooked_geometry refuses
    # to cook a dirty node, and reading display.geometry() here would cook it
    # first, making the guard report "clean" for a node that was never cooked.
    coverage = udim_info(hou, node_path)
    geo = cooked_geometry(display)
    # Derive uv_layers from the same geometry udim_info already resolved, so both
    # UV fields in this payload come from one convention. Going back through
    # check_uvs would re-read displayNode().geometry() a second time and cook a
    # node that cooked_geometry just refused, giving has_uvs=true next to
    # udim_detection=unavailable.
    uv_layers = uv_attribute_names(geo) if geo is not None else []
    prim_count = len(geo.iterPrims()) if geo is not None else 0

    info = {
        "path": node_path,
        "name": node.name(),
        "type": "obj" if node_path.startswith("/obj") else "sop",
        "has_display_geo": True,
        "geometry_available": geo is not None,
        "has_uvs": bool(uv_layers),
        "uv_layers": uv_layers,
        "primitive_count": prim_count,
        "bake_ready": bool(uv_layers) and prim_count > 0,
    }
    info.update(coverage)
    return info


def udim_info(hou: Any, node_path: str) -> dict:
    """UDIM coverage for a bake target, in the same terms ``inspect_uv`` uses.

    Returns ``udim_tiles``, ``udim_tile_count`` and a ``udim_detection`` value of
    ``computed``, ``no_values``, ``no_uv_sets`` or ``unavailable`` so a caller can
    tell "no tiles" from "could not read the tiles".
    """
    empty = {
        "udim_tiles": [],
        "udim_tile_count": 0,
        "udim_detection": "unavailable",
        "needs_udim_output": False,
        "sampled_uv_set": None,
    }
    node = hou.node(node_path)
    if node is None:
        return empty
    display = node.displayNode() if hasattr(node, "displayNode") else None
    target = display if display is not None else node
    geometry = cooked_geometry(target)
    if geometry is None:
        return empty
    names = uv_attribute_names(geometry, max_names=1)
    if not names:
        return dict(empty, udim_detection="no_uv_sets")
    values = uv_values(geometry, names[0])
    if values is None:
        return dict(empty, udim_detection="no_values", sampled_uv_set=names[0])
    tiles = udim_tiles(values)
    return {
        "udim_tiles": tiles,
        "udim_tile_count": len(tiles),
        "udim_detection": "computed",
        "needs_udim_output": len(tiles) > UDIM_OUTPUT_THRESHOLD,
        "sampled_uv_set": names[0],
    }


def bake_output_paths(output_path: str, tiles) -> List[str]:
    """Concrete output paths for each UDIM tile, or the path itself when flat."""
    if not output_path or UDIM_TOKEN not in output_path:
        return [output_path] if output_path else []
    return [output_path.replace(UDIM_TOKEN, str(tile)) for tile in tiles]


def create_or_get_bake_rop(hou: Any, rop_path: str) -> Any:
    """Create a Bake Texture ROP if one doesn't already exist at *rop_path*.

    Tries baker::2.0 first, then game_simple_baker.
    """
    node, _created = create_or_get_bake_rop_ex(hou, rop_path)
    return node


def create_or_get_bake_rop_ex(hou: Any, rop_path: str) -> Tuple[Any, bool]:
    """``create_or_get_bake_rop`` plus whether this call created the node.

    Callers that can fail after creating the ROP use this so a failed request
    destroys exactly what it made and leaves a pre-existing ROP untouched.
    """
    node = hou.node(rop_path)
    if node is not None:
        return node, False

    for type_name in ("baker::2.0", "game_simple_baker", "bake_texture"):
        try:
            node = ensure_node(hou, rop_path, type_name)
            if node is not None:
                return node, True
        except Exception:
            continue

    raise ValueError(
        "No bake ROP type available. Tried: baker::2.0, game_simple_baker, bake_texture. "
        "Install Houdini Game Dev Toolset or sidefx_labs."
    )


def write_file_list(
    output_dir: str, prefix: str, file_format: str, object_names: List[str], map_types: List[str]
) -> List[str]:
    """Generate expected output file paths for a multi-map multi-object bake."""
    files = []
    for obj_name in object_names:
        safe = obj_name.replace("/", "_").replace(":", "_")
        for mt in map_types:
            files.append(os.path.join(output_dir, "{}_{}_{}.{}".format(prefix, safe, mt, file_format)))
    return files


def node_summary(hou: Any, node_path: str) -> Optional[dict]:
    """Return a small, JSON-safe node summary."""
    node = hou.node(node_path)
    if node is None:
        return None
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }
