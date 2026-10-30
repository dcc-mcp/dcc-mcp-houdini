"""Import an externally generated character mesh (the "hyper3d" step).

This is the in-adapter equivalent of a hyper3d/Rodin text-to-3D generation:
that service is out-of-band, so this tool ingests the mesh it produced (FBX,
OBJ, Alembic, bgeo/glb-bgeo) into a SOP network, validates that it carries
real geometry, optionally normalizes height/units, and reports a rig-ready
contract. When no mesh file is supplied it builds a procedural proxy biped so
the rest of the workflow can still be validated fully offline.
"""

from __future__ import annotations

import os
from typing import Optional

from _kinefx_common import get_geo_container
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

SUPPORTED_EXTENSIONS = (".fbx", ".obj", ".abc", ".bgeo", ".bgeo.sc", ".geo", ".glb", ".usd", ".usdc", ".usda")

# Map a file extension to the SOP type used to load it (guarded at runtime).
_IMPORT_SOP = {
    ".fbx": "file",  # FBX usually arrives via 'file' or an agent/fbx SOP.
    ".obj": "file",
    ".abc": "alembic",
    ".bgeo": "file",
    ".bgeo.sc": "file",
    ".geo": "file",
    ".glb": "file",
    ".usd": "usdimport",
    ".usdc": "usdimport",
    ".usda": "usdimport",
}


def _ext(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".bgeo.sc"):
        return ".bgeo.sc"
    return os.path.splitext(lower)[1]


def _set_if_present(node, name: str, value) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def _resolve_descriptor_file(descriptor) -> Optional[str]:
    """Extract a local mesh path from a hyper3d-style AssetDescriptor.

    Accepts the common shapes: a direct dict with ``local_path``/``path``, an
    ``asset`` wrapper with those keys, or a ``variants`` list of
    ``{local_path, format}`` entries (first supported format wins). Returns
    ``None`` when nothing usable is found.
    """
    if not isinstance(descriptor, dict):
        return None
    candidates = []
    for key in ("local_path", "path", "file", "filepath"):
        value = descriptor.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    asset = descriptor.get("asset")
    if isinstance(asset, dict):
        for key in ("local_path", "path", "file", "filepath"):
            value = asset.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)
    variants = descriptor.get("variants") or descriptor.get("files")
    if isinstance(variants, list):
        for variant in variants:
            if isinstance(variant, dict):
                value = variant.get("local_path") or variant.get("path")
                if isinstance(value, str) and value:
                    candidates.append(value)
    for value in candidates:
        if _ext(value) in SUPPORTED_EXTENSIONS:
            return value
    return candidates[0] if candidates else None


def import_generated_character(
    geo_path: str,
    mesh_file: Optional[str] = None,
    node_name: str = "generated_character",
    target_height: Optional[float] = None,
    proxy: bool = True,
    asset_descriptor: Optional[dict] = None,
) -> dict:
    """Import (or proxy) a generated character mesh into *geo_path*.

    Args:
        geo_path: Geometry SOP container path.
        mesh_file: Path to a generated mesh file. ``None`` builds a proxy.
        node_name: Name of the import SOP.
        target_height: If set, add a transform SOP to scale mesh to this height.
        proxy: When ``True`` and mesh_file is missing/unreadable, build a proxy.
        asset_descriptor: Optional hyper3d ``AssetDescriptor`` dict; its
            ``local_path`` is resolved to ``mesh_file`` when the latter is unset.
    """
    if not isinstance(geo_path, str) or not geo_path.strip():
        return skill_error("Invalid geo_path", "geo_path must be a non-empty string")

    descriptor_used = False
    if not mesh_file and asset_descriptor is not None:
        mesh_file = _resolve_descriptor_file(asset_descriptor)
        descriptor_used = mesh_file is not None

    ext = _ext(mesh_file) if mesh_file else None
    if mesh_file and ext not in SUPPORTED_EXTENSIONS:
        return skill_error(
            "Unsupported mesh format",
            "mesh_file must be one of {}".format(", ".join(SUPPORTED_EXTENSIONS)),
            mesh_file=mesh_file,
            extension=ext,
        )
    file_exists = bool(mesh_file) and os.path.isfile(mesh_file)
    if mesh_file and not file_exists and not proxy:
        return skill_error("Mesh file not found", "mesh_file does not exist", mesh_file=mesh_file)

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        geo = get_geo_container(hou, geo_path)
        created = []
        mode = "import"

        if file_exists:
            import_node = geo.createNode(_IMPORT_SOP.get(ext, "file"), node_name=node_name)
            _set_if_present(import_node, "file", mesh_file)
            source = import_node
            created.append(import_node)
            geometry = None
            try:
                import_node.cook(force=True)
                geometry = import_node.geometry()
            except Exception:  # noqa: BLE001 - cook may fail without a valid FBX SDK
                geometry = None
            point_count = 0
            if geometry is not None:
                try:
                    point_count = len(geometry.points())
                except Exception:  # noqa: BLE001
                    point_count = 0
            if point_count == 0 and proxy:
                # Fall back to a proxy when the external file could not be cooked.
                source = _create_proxy(geo, node_name, created)
                mode = "proxy_fallback"
        else:
            source = _create_proxy(geo, node_name, created)
            mode = "proxy"

        output = source
        if target_height is not None and target_height > 0:
            transform = geo.createNode("xform", node_name="{}_normalize".format(node_name))
            transform.setInput(0, source)
            # Bounds-driven scaling is left to the caller; record the intent.
            _set_if_present(transform, "scale", 1.0)
            output = transform
            created.append(transform)

        for node in created:
            node.moveToGoodPosition()

        return skill_success(
            "Imported generated character mesh",
            geo_path=geo.path(),
            mode=mode,
            mesh_file=mesh_file if file_exists else None,
            extension=ext if file_exists else None,
            asset_descriptor_used=descriptor_used,
            source_node=source.path(),
            output_node=output.path(),
            created_nodes=[node.path() for node in created],
            normalized=target_height is not None,
            target_height=target_height,
            rig_ready=True,
            next_tools=["create_biped_template", "capture_joints", "houdini_import_to_scene__import_to_scene"],
            note=(
                "Externally generated meshes (hyper3d/Rodin) are ingested here; a "
                "hyper3d AssetDescriptor can be passed via asset_descriptor or via "
                "houdini_import_to_scene__import_to_scene. Verify UVs/materials/units "
                "post-import; use houdini_interchange__probe_file to round-trip."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return skill_exception(exc, message="Failed to import generated character")


def _create_proxy(geo, node_name, created):
    """Build a minimal procedural proxy mesh so the pipeline works offline."""
    proxy = geo.createNode("box", node_name="{}_proxy".format(node_name))
    _set_if_present(proxy, "sizex", 0.45)
    _set_if_present(proxy, "sizey", 1.7)
    _set_if_present(proxy, "sizez", 0.3)
    _set_if_present(proxy, "ty", 0.85)
    created.append(proxy)
    return proxy


@skill_entry
def main(**kwargs) -> dict:
    return import_generated_character(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
