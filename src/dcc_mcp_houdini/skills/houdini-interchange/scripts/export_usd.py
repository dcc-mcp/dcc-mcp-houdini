"""Export a LOP node's USD stage to disk and report the root layer."""

from __future__ import annotations

import os
from typing import List, Optional

from _io_common import ensure_parent_dir, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _root_layer_identifier(stage) -> Optional[str]:
    try:
        layer = stage.GetRootLayer()
    except Exception:  # noqa: BLE001
        return None
    for attr in ("identifier", "realPath"):
        value = getattr(layer, attr, None)
        if value:
            return value
    return None


def export_usd(
    lop_node_path: str,
    output_path: str,
    frame_range: Optional[List[float]] = None,
    create_dirs: bool = True,
) -> dict:
    """Export the composed stage of a LOP node (``node.stage()``) to USD."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, lop_node_path)
        stage_fn = getattr(node, "stage", None)
        if not callable(stage_fn):
            return skill_error(
                "Not a LOP node",
                "Node has no stage(); USD export requires a LOP/Solaris node",
                node_path=node.path(),
            )
        stage = stage_fn()
        if stage is None:
            return skill_error(
                "No USD stage",
                "LOP node produced no stage to export",
                node_path=node.path(),
            )
        root_layer = _root_layer_identifier(stage)
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
            "Exported USD stage",
            node_path=node.path(),
            output_path=output_path,
            root_layer=root_layer,
            frame_range=list(frame_range) if frame_range else None,
            written_files=written,
            skipped=skipped,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export USD stage")


@skill_entry
def main(**kwargs) -> dict:
    return export_usd(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
