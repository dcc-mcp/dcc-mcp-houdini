"""Bounded Houdini adapter for dcc-mcp-core Asset Sync."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_USD_FORMATS = {
    "usd": "model/vnd.usd",
    "usda": "model/vnd.usda",
    "usdc": "model/vnd.usdc",
    "usdz": "model/vnd.usdz+zip",
}


def _core_types() -> Tuple[Any, Any, Any]:
    try:
        from dcc_mcp_core.asset_sync import AssetSyncConflictError, AssetSyncValidationError, FileAssetSyncStore
    except ImportError as exc:
        raise RuntimeError(
            "This runtime does not include dcc_mcp_core.asset_sync; install a Core build containing Asset Sync"
        ) from exc
    return FileAssetSyncStore, AssetSyncConflictError, AssetSyncValidationError


def _configured_root(name: str) -> Path:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError("{} is not configured".format(name))
    return Path(value).expanduser().resolve()


def _safe_relative(root: Path, value: str) -> Path:
    relative = Path(str(value).replace("\\", "/"))
    if relative.is_absolute() or not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError("source_name must be a safe relative path")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("source_name escapes the configured source root") from exc
    return resolved


def _usd_metadata(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    extension = path.suffix.lower().lstrip(".")
    if extension not in _USD_FORMATS:
        raise ValueError("Asset Sync accepts only USD, USDA, USDC, or USDZ")
    metadata: Dict[str, Any] = {
        "interchange": {
            "format": extension,
            "preserves": ["animation", "basis_curves", "usd_skel", "usd_shade", "material_bindings", "composition"],
        }
    }
    spatial: Dict[str, Any] = {}
    try:
        from pxr import Usd, UsdGeom

        stage = Usd.Stage.Open(str(path))
        if not stage:
            raise ValueError("USD stage could not be opened")
        spatial = {
            "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
            "up_axis": str(UsdGeom.GetStageUpAxis(stage)).upper(),
        }
        metadata["timeline"] = {
            "start": float(stage.GetStartTimeCode()),
            "end": float(stage.GetEndTimeCode()),
            "frames_per_second": float(stage.GetFramesPerSecond()),
        }
        counts = {"prims": 0, "curves": 0, "skeletons": 0, "materials": 0}
        for prim in stage.Traverse():
            counts["prims"] += 1
            name = prim.GetTypeName()
            if name in ("BasisCurves", "NurbsCurves"):
                counts["curves"] += 1
            elif name in ("Skeleton", "SkelRoot"):
                counts["skeletons"] += 1
            elif name == "Material":
                counts["materials"] += 1
        metadata["usd_counts"] = counts
    except ImportError:
        metadata["inspection_warning"] = "pxr is unavailable; stage metadata was not inspected"
    return spatial, metadata


def publish_usd_revision(
    channel_id: str,
    asset_id: str,
    source_name: str,
    expected_head_revision: int,
    source_instance_id: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        source = _safe_relative(_configured_root("DCC_MCP_HOUDINI_ASSET_SYNC_SOURCE_ROOT"), source_name)
        if not source.is_file():
            raise FileNotFoundError(str(source))
        spatial, inspected = _usd_metadata(source)
        inspected.update(dict(metadata or {}))
        Store, _, _ = _core_types()
        revision = Store(_configured_root("DCC_MCP_ASSET_SYNC_ROOT")).publish(
            source,
            channel_id=channel_id,
            asset_id=asset_id,
            format=source.suffix.lstrip("."),
            mime=_USD_FORMATS[source.suffix.lower().lstrip(".")],
            expected_head_revision=expected_head_revision,
            source_instance_id=source_instance_id or os.environ.get("DCC_MCP_INSTANCE_ID"),
            spatial=spatial,
            metadata=inspected,
        )
        return skill_success("Published Asset Sync revision {}".format(revision.revision), revision=revision.to_dict())
    except Exception as exc:
        return skill_exception(exc, message="Failed to publish USD revision")


def read_asset_head(channel_id: str, asset_id: str) -> Dict[str, Any]:
    try:
        Store, _, _ = _core_types()
        head = Store(_configured_root("DCC_MCP_ASSET_SYNC_ROOT")).read_head(channel_id, asset_id)
        if head is None:
            return skill_error("Asset has not been published", "No head exists for the requested channel and asset")
        return skill_success("Asset Sync head is revision {}".format(head.revision), revision=head.to_dict())
    except Exception as exc:
        return skill_exception(exc, message="Failed to read Asset Sync head")


def reference_usd_revision(
    channel_id: str,
    asset_id: str,
    stage_path: str = "/stage",
    node_name: Optional[str] = None,
    primitive_path: str = "/",
    subfolder: str = "",
) -> Dict[str, Any]:
    try:
        import hou

        Store, _, _ = _core_types()
        store = Store(_configured_root("DCC_MCP_ASSET_SYNC_ROOT"))
        head = store.read_head(channel_id, asset_id)
        if head is None:
            return skill_error("Asset has not been published", "No head exists for the requested channel and asset")
        if head.format not in _USD_FORMATS:
            return skill_error("Unsupported revision format", "Houdini reference mode requires USD")
        materialized = store.materialize(
            head, _configured_root("DCC_MCP_HOUDINI_ASSET_SYNC_CONSUMER_ROOT"), subfolder=subfolder
        )
        parent = hou.node(stage_path)
        if parent is None:
            return skill_error("Solaris stage network not found", stage_path)
        node = parent.createNode("reference", node_name=node_name or "sync_{}".format(asset_id.replace("-", "_")))
        for parm_name in ("filepath1", "filepath"):
            parm = node.parm(parm_name)
            if parm is not None:
                parm.set(str(materialized))
                break
        prim_parm = node.parm("primpath")
        if prim_parm is not None:
            prim_parm.set(primitive_path)
        node.setDisplayFlag(True)
        node.setRenderFlag(True)
        return skill_success(
            "Referenced Asset Sync revision {}".format(head.revision),
            revision=head.to_dict(),
            node_path=node.path(),
            materialized_name=materialized.name,
            editability_mode="usd_proxy",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to reference Asset Sync revision")


@skill_entry
def main(**kwargs: Any) -> Dict[str, Any]:
    operation = kwargs.pop("operation", None)
    if operation == "read_asset_head":
        return read_asset_head(**kwargs)
    if operation == "reference_usd_revision":
        return reference_usd_revision(**kwargs)
    return publish_usd_revision(**kwargs)
