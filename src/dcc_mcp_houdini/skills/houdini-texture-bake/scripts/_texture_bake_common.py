"""Shared helpers for Houdini texture-bake skills.

Detects available bake methods, creates ROPs, validates UVs, and provides
common utilities for all bake scripts.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional, Sequence, Tuple

# Map-type vocabulary shared across bake_textures and transfer_maps.
# Labs Maps Baker supports ~20+ types; Bake Texture ROP supports a subset.
_MAP_TYPE_VOCABULARY = {
    "normals", "cavity", "curvature", "diffuse", "roughness",
    "metallic", "thickness", "world_position", "opacity",
    "ambient_occlusion", "displacement", "height", "emission",
    "scattering", "transmission", "basecolor", "specular",
    "subsurface", "anisotropy", "coat", "sheen",
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
        "recommendations": (
            []
            if labs
            else ["Install sidefx_labs for Labs Maps Baker (richest map-type support)."]
        ),
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
    for attr in geo.pointAttribs():
        if attr.dataType() == hou.attribData.Float and attr.size() >= 2:
            if "uv" in attr.name().lower():
                uv_names.append(attr.name())
    for attr in geo.vertexAttribs():
        if attr.dataType() == hou.attribData.Float and attr.size() >= 2:
            if "uv" in attr.name().lower():
                uv_names.append(attr.name())
    return uv_names


def bake_geometry_info(hou: Any, node_path: str) -> Optional[dict]:
    """Return bake-relevant info dict for a single geometry node, or None."""
    node = hou.node(node_path)
    if node is None:
        return None
    display = node.displayNode() if hasattr(node, "displayNode") else None
    if display is None:
        return {
            "path": node_path,
            "name": node.name(),
            "type": "obj",
            "has_display_geo": False,
            "has_uvs": False,
            "uv_layers": [],
            "primitive_count": 0,
            "bake_ready": False,
        }

    geo = display.geometry()
    uv_layers = check_uvs(hou, node_path) or []
    prim_count = len(geo.iterPrims()) if geo is not None else 0

    return {
        "path": node_path,
        "name": node.name(),
        "type": "obj" if node_path.startswith("/obj") else "sop",
        "has_display_geo": True,
        "has_uvs": bool(uv_layers),
        "uv_layers": uv_layers,
        "primitive_count": prim_count,
        "bake_ready": bool(uv_layers) and prim_count > 0,
    }


def create_or_get_bake_rop(hou: Any, rop_path: str) -> Any:
    """Create a Bake Texture ROP if one doesn't already exist at *rop_path*.

    Tries baker::2.0 first, then game_simple_baker.
    """
    node = hou.node(rop_path)
    if node is not None:
        return node

    for type_name in ("baker::2.0", "game_simple_baker", "bake_texture"):
        try:
            node = ensure_node(hou, rop_path, type_name)
            if node is not None:
                return node
        except Exception:
            continue

    raise ValueError(
        "No bake ROP type available. Tried: baker::2.0, game_simple_baker, bake_texture. "
        "Install Houdini Game Dev Toolset or sidefx_labs."
    )


def write_file_list(output_dir: str, prefix: str, file_format: str,
                    object_names: List[str], map_types: List[str]) -> List[str]:
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
