"""Export a SOP node's geometry to USD through a transient SOP Import LOP.

The typed interchange layer could author SOP geometry (``create_primitive``,
``houdini-mesh-ops``) and export a composed LOP stage (``export_usd``), but had
no tool to bridge the two: ``export_usd`` requires a LOP node with ``stage()``.
This tool creates a transient ``sopimport`` LOP in a LOP network, points it at
the source SOP, composes the USD stage, exports it, reports a point/prim-count
readback, then removes the transient nodes so the user's scene is left clean.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from _io_common import ensure_parent_dir, set_first_parm  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _source_counts(node: Any) -> dict:
    """Return point and primitive counts from a SOP node's cooked geometry."""
    geo = node.geometry() if hasattr(node, "geometry") else None
    if geo is None:
        return {"source_point_count": None, "source_primitive_count": None}
    points = len(geo.points()) if hasattr(geo, "points") else None
    prims = len(geo.prims()) if hasattr(geo, "prims") else None
    return {"source_point_count": points, "source_primitive_count": prims}


def _stage_prim_count(stage: Any) -> Optional[int]:
    """Count prims in the composed USD stage (best effort, never fatal)."""
    if stage is None or not hasattr(stage, "Traverse"):
        return None
    try:
        return sum(1 for _ in stage.Traverse())
    except Exception:  # noqa: BLE001
        return None


def export_sop_to_usd(
    node_path: str,
    output_path: str,
    prim_path: str = "/ASSET/geo",
    lop_parent_path: str = "/stage",
    create_dirs: bool = True,
) -> dict:
    """Author the cooked geometry of *node_path* (a SOP) into a USD file."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    transient: List[Any] = []
    try:
        sop_node = hou.node(node_path)
        if sop_node is None:
            return skill_error(
                "SOP node not found",
                "No node at the given SOP path",
                node_path=node_path,
            )
        source = _source_counts(sop_node)
        if source["source_point_count"] is None and source["source_primitive_count"] is None:
            return skill_error(
                "No SOP geometry",
                "Node has no cooked geometry to export",
                node_path=node_path,
            )

        lop_parent = hou.node(lop_parent_path)
        if lop_parent is None:
            root = hou.node("/")
            lop_parent = root.createNode("lopnet", node_name="sop_to_usd_lopnet")
            transient.append(lop_parent)

        sopimport = lop_parent.createNode("sopimport", node_name="sop_to_usd_import")
        transient.append(sopimport)
        if set_first_parm(sopimport, ("soppath",), node_path) is None:
            return skill_error(
                "Could not set SOP path",
                "SOP Import LOP has no recognised soppath parm",
                node_path=sopimport.path(),
            )
        set_first_parm(sopimport, ("primpath", "destpath"), prim_path)
        if hasattr(sopimport, "cook"):
            sopimport.cook(force=True)

        stage_fn = getattr(sopimport, "stage", None)
        if not callable(stage_fn):
            return skill_error(
                "No USD stage",
                "SOP Import LOP has no stage() to compose",
                node_path=sopimport.path(),
            )
        stage = stage_fn()
        if stage is None:
            return skill_error(
                "No USD stage",
                "SOP Import LOP produced no composed stage",
                node_path=sopimport.path(),
            )

        if create_dirs:
            ensure_parent_dir(output_path)
        warnings: List[str] = []
        try:
            stage.Export(output_path)
        except Exception as export_exc:  # noqa: BLE001
            warnings.append("Stage export failed: {}".format(export_exc))
        written = [output_path] if os.path.isfile(output_path) else []
        skipped = [] if written else [output_path]
        return skill_success(
            "Exported SOP geometry to USD",
            node_path=node_path,
            output_path=output_path,
            prim_path=prim_path,
            source_point_count=source["source_point_count"],
            source_primitive_count=source["source_primitive_count"],
            stage_prim_count=_stage_prim_count(stage),
            written_files=written,
            skipped=skipped,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export SOP geometry to USD")
    finally:
        for node in reversed(transient):
            try:
                node.destroy()
            except Exception:  # noqa: BLE001
                pass


@skill_entry
def main(**kwargs) -> dict:
    return export_sop_to_usd(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
