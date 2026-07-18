"""Scan for bake-compatible geometry nodes. Read-only, sync."""

from __future__ import annotations

from _texture_bake_common import (  # noqa: E402
    bake_geometry_info,
    detect_bake_methods,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_bake_targets(
    node_type_filter: str = "obj",
    require_uvs: bool = False,
) -> dict:
    """Scan scene geometry and report bake-compatible nodes with UV info."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        methods = detect_bake_methods(hou)
        targets = []

        if node_type_filter in ("obj", "all"):
            obj_root = hou.node("/obj")
            if obj_root is not None:
                for child in obj_root.children():
                    info = bake_geometry_info(hou, child.path())
                    if info is None:
                        continue
                    if node_type_filter == "all" and info.get("has_display_geo"):
                        sop_node = child.displayNode()
                        if sop_node is not None:
                            sop_info = bake_geometry_info(hou, sop_node.path())
                            if sop_info:
                                sop_info["parent_obj"] = child.path()
                                targets.append(sop_info)
                    if info.get("has_display_geo", False):
                        targets.append(info)

        if node_type_filter in ("sop", "all"):
            # Scan SOP networks inside OBJ containers
            obj_root = hou.node("/obj")
            if obj_root is not None:
                for child in obj_root.children():
                    display = child.displayNode() if hasattr(child, "displayNode") else None
                    if display is not None:
                        info = bake_geometry_info(hou, display.path())
                        if info is not None and info.get("primitive_count", 0) > 0:
                            if child.path() not in {t["path"] for t in targets}:
                                info["parent_obj"] = child.path()
                                targets.append(info)

        if require_uvs:
            targets = [t for t in targets if t.get("has_uvs", False)]

        bake_ready = [t for t in targets if t.get("bake_ready", False)]
        methods_info = {
            k: v
            for k, v in methods.items()
            if k
            in (
                "labs_maps_baker_available",
                "bake_texture_rop_available",
                "available_methods",
                "recommended",
                "recommendations",
            )
        }

        return skill_success(
            "Found {} bake target(s) ({} bake-ready)".format(
                len(targets),
                len(bake_ready),
            ),
            targets=targets,
            bake_ready_count=len(bake_ready),
            total_count=len(targets),
            methods=methods_info,
            prompt="Pick bake-ready targets with UVs, then use bake_textures, bake_ambient_occlusion, or bake_lighting.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list bake targets")


@skill_entry
def main(**kwargs) -> dict:
    return list_bake_targets(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
