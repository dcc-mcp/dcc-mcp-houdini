"""List a bounded portion of a composed Solaris USD Stage."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _usd_common import require_absolute_path, require_range, resolve_prim, resolve_stage  # noqa: E402


def _has_children(Usd: Any, prim: Any) -> bool:
    probe = iter(Usd.PrimRange(prim))
    next(probe, None)  # PrimRange includes its root.
    return next(probe, None) is not None


def _prim_summary(prim: Any, depth: int) -> dict:
    return {
        "path": str(prim.GetPath()),
        "name": str(prim.GetName()),
        "type_name": str(prim.GetTypeName()),
        "depth": depth,
        "active": bool(prim.IsActive()),
        "defined": bool(prim.IsDefined()),
        "loaded": bool(prim.IsLoaded()),
        "instance": bool(prim.IsInstance()),
        "instance_proxy": bool(prim.IsInstanceProxy()),
    }


def list_stage_prims(
    lop_node_path: str,
    root_path: str = "/",
    max_depth: int = 3,
    limit: int = 200,
) -> dict:
    """Return at most *limit* descendants up to *max_depth*."""
    try:
        import hou  # noqa: PLC0415
        from pxr import Usd  # noqa: PLC0415
    except ImportError as exc:
        return skill_error("Houdini USD APIs not available", str(exc))

    try:
        require_range(max_depth, "max_depth", 1, 16)
        require_range(limit, "limit", 1, 500)
        usd_root = require_absolute_path(root_path, "root_path")
        node, stage = resolve_stage(hou, lop_node_path)
        root = stage.GetPseudoRoot() if usd_root == "/" else resolve_prim(stage, usd_root)
        root_depth = root.GetPath().pathElementCount
        traversal = iter(Usd.PrimRange(root))
        next(traversal, None)  # The requested root is context, not a result row.
        prims = []
        depth_truncated = False

        while len(prims) < limit:
            prim = next(traversal, None)
            if prim is None:
                break
            depth = prim.GetPath().pathElementCount - root_depth
            prims.append(_prim_summary(prim, depth))
            if depth >= max_depth:
                depth_truncated = depth_truncated or _has_children(Usd, prim)
                traversal.PruneChildren()

        limit_truncated = len(prims) == limit and next(traversal, None) is not None
        truncation_reasons = []
        if limit_truncated:
            truncation_reasons.append("limit")
        if depth_truncated:
            truncation_reasons.append("max_depth")

        return skill_success(
            "Listed USD Stage prims",
            lop_node_path=str(node.path()),
            root_path=usd_root,
            prims=prims,
            returned_count=len(prims),
            truncated=bool(truncation_reasons),
            truncation_reasons=truncation_reasons,
            bounds={"max_depth": max_depth, "limit": limit},
        )
    except ValueError as exc:
        return skill_error("Invalid USD Stage query", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to list USD Stage prims")


@skill_entry
def main(**kwargs) -> dict:
    return list_stage_prims(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
