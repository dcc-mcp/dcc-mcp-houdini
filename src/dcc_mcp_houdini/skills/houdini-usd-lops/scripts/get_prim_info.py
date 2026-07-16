"""Inspect one prim on a composed Solaris USD Stage."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _usd_common import make_time_code, resolve_prim, resolve_stage  # noqa: E402


def _vector(value: Any, length: int) -> list:
    return [float(value[index]) for index in range(length)]


def _world_transform(UsdGeom: Any, prim: Any, time: Any) -> Optional[list]:
    if not UsdGeom.Xformable(prim):
        return None
    matrix = UsdGeom.XformCache(time).GetLocalToWorldTransform(prim)
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _world_bounds(UsdGeom: Any, prim: Any, time: Any) -> Optional[dict]:
    purposes = [
        UsdGeom.Tokens.default_,
        UsdGeom.Tokens.proxy,
        UsdGeom.Tokens.render,
        UsdGeom.Tokens.guide,
    ]
    aligned = UsdGeom.BBoxCache(time, purposes, useExtentsHint=True).ComputeWorldBound(prim).ComputeAlignedRange()
    if aligned.IsEmpty():
        return None
    return {"min": _vector(aligned.GetMin(), 3), "max": _vector(aligned.GetMax(), 3)}


def _visibility(UsdGeom: Any, prim: Any, time: Any) -> Optional[str]:
    imageable = UsdGeom.Imageable(prim)
    return str(imageable.ComputeVisibility(time)) if imageable else None


def _material_path(UsdShade: Any, prim: Any) -> Optional[str]:
    binding = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    material = binding[0] if isinstance(binding, tuple) else binding
    return str(material.GetPath()) if material else None


def get_prim_info(lop_node_path: str, prim_path: str, time_code: Optional[float] = None) -> dict:
    """Return typed read-only information for one USD prim."""
    try:
        import hou  # noqa: PLC0415
        from pxr import Usd, UsdGeom, UsdShade  # noqa: PLC0415
    except ImportError as exc:
        return skill_error("Houdini USD APIs not available", str(exc))

    try:
        node, stage = resolve_stage(hou, lop_node_path)
        prim = resolve_prim(stage, prim_path)
        usd_time = make_time_code(Usd, time_code)
        info = {
            "path": str(prim.GetPath()),
            "name": str(prim.GetName()),
            "type_name": str(prim.GetTypeName()),
            "active": bool(prim.IsActive()),
            "defined": bool(prim.IsDefined()),
            "loaded": bool(prim.IsLoaded()),
            "instance": bool(prim.IsInstance()),
            "instance_proxy": bool(prim.IsInstanceProxy()),
            "visibility": _visibility(UsdGeom, prim, usd_time),
            "world_transform": _world_transform(UsdGeom, prim, usd_time),
            "world_bounds": _world_bounds(UsdGeom, prim, usd_time),
            "material_binding": _material_path(UsdShade, prim),
        }
        return skill_success(
            "Inspected USD prim",
            lop_node_path=str(node.path()),
            time_code="default" if time_code is None else float(time_code),
            prim=info,
        )
    except ValueError as exc:
        return skill_error("Invalid USD prim query", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect USD prim")


@skill_entry
def main(**kwargs) -> dict:
    return get_prim_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
