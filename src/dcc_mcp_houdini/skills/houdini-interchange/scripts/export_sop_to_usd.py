"""Export a SOP node's geometry to USD through a transient SOP Import LOP.

The typed interchange layer could author SOP geometry (``create_primitive``,
``houdini-mesh-ops``) and export a composed LOP stage (``export_usd``), but had
no tool to bridge the two: ``export_usd`` requires a LOP node with ``stage()``.
This tool creates a transient ``sopimport`` LOP in a LOP network, points it at
the source SOP, composes the USD stage, exports it, reports counts, then removes
the transient nodes so the user's scene is left clean.

The prim-count readback is the **in-memory composed stage** only. A best-effort
disk readback (``Usd.Stage.Open``) is attempted and reported separately.
``Usd.Stage.Export`` flattens the stage to a single layer; it is not equivalent
to a full USD ROP save. Native end-to-end validation under hython remains a
separate acceptance gate and is not established by these reported counts.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional, Tuple

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


def _composed_stage_prim_count(stage: Any) -> Optional[int]:
    """Count prims in the in-memory composed USD stage (best effort)."""
    if stage is None or not hasattr(stage, "Traverse"):
        return None
    try:
        return sum(1 for _ in stage.Traverse())
    except Exception:  # noqa: BLE001
        return None


def _disk_prim_count(output_path: str) -> Tuple[Optional[int], str]:
    """Best-effort readback of the written file via pxr.Usd.Stage.Open.

    Returns ``(count, status)``; ``count`` is None when pxr is unavailable or
    the file cannot be opened. Houdini exposes USD as ``pxr.*`` only.
    """
    try:
        from pxr import Usd  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - pxr is unavailable outside Houdini
        return None, "pxr_unavailable"
    open_fn = getattr(getattr(Usd, "Stage", None), "Open", None)
    if not callable(open_fn):
        return None, "pxr_unavailable"
    try:
        disk_stage = open_fn(output_path)
    except Exception:  # noqa: BLE001
        return None, "open_failed"
    if disk_stage is None:
        return None, "open_failed"
    try:
        return sum(1 for _ in disk_stage.Traverse()), "ok"
    except Exception:  # noqa: BLE001
        return None, "traverse_failed"


def _prim_is_valid(stage: Any, prim_path: str) -> Optional[bool]:
    """Best-effort check that *prim_path* exists on the composed stage."""
    getter = getattr(stage, "GetPrimAtPath", None)
    if not callable(getter) or not prim_path:
        return None
    try:
        prim = getter(prim_path)
        is_valid = getattr(prim, "IsValid", None)
        return bool(is_valid()) if callable(is_valid) else None
    except Exception:  # noqa: BLE001
        return None


def _write_signature(path: str) -> Optional[Tuple[int, int]]:
    """Return ``(mtime_ns, size)`` for a file, or None when it is absent."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


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
        # Report which destination-prim parm was actually set, not just what the
        # caller asked for; SOP Import LOP parm tokens vary across Houdini builds.
        prim_path_parm = set_first_parm(sopimport, ("primpath", "destpath"), prim_path)
        prim_path_applied = prim_path_parm is not None
        warnings: List[str] = []
        if not prim_path_applied:
            warnings.append(
                "prim_path was not applied: SOP Import LOP exposes no "
                "primpath/destpath parm; verify the destination prim in the USD."
            )
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

        # F1: only report success for a *fresh* write. Capture the pre-export
        # file signature, fail on any Export exception, and require that a new
        # non-empty file (or a changed one) actually appeared. This prevents a
        # stale file at output_path from being reported as this run's output.
        previous = _write_signature(output_path)
        try:
            stage.Export(output_path)
        except Exception as export_exc:  # noqa: BLE001
            return skill_error(
                "USD export failed",
                "stage.Export raised: {}".format(export_exc),
                node_path=node_path,
                output_path=output_path,
            )
        current = _write_signature(output_path)
        written = current is not None and current[1] > 0 and (previous is None or current != previous)
        if not written:
            return skill_error(
                "USD export did not write a file",
                "stage.Export produced no new non-empty file at the output path",
                node_path=node_path,
                output_path=output_path,
            )

        disk_count, disk_status = _disk_prim_count(output_path)
        if disk_status != "ok":
            warnings.append(
                "Disk readback unavailable ({}); prim counts are from the in-memory composed stage only.".format(
                    disk_status
                )
            )

        return skill_success(
            "Exported SOP geometry to USD",
            node_path=node_path,
            output_path=output_path,
            prim_path=prim_path,
            prim_path_applied=prim_path_applied,
            prim_path_parm=prim_path_parm,
            prim_path_valid=_prim_is_valid(stage, prim_path),
            source_point_count=source["source_point_count"],
            source_primitive_count=source["source_primitive_count"],
            composed_stage_prim_count=_composed_stage_prim_count(stage),
            composed_stage_prim_count_scope="in_memory_composed_stage",
            disk_prim_count=disk_count,
            disk_readback_status=disk_status,
            stage_export="flattened_single_layer_via_stage_export",
            written_files=[output_path],
            skipped=[],
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
