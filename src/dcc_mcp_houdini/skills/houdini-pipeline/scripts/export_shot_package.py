"""Export a shot/package manifest (frame range, cameras, ROPs, caches)."""

from __future__ import annotations

import json
import os
from typing import Optional

from _pipeline_common import expand_path, iter_file_parms, resolve_nodes  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _collect_typed(hou, type_tokens):
    """Return node paths whose type name contains any of *type_tokens*."""
    matches = []
    for node in resolve_nodes(hou, None):
        try:
            type_name = node.type().name().lower()
        except Exception:  # noqa: BLE001
            continue
        if any(tok in type_name for tok in type_tokens):
            matches.append(node.path())
    return matches


def export_shot_package(
    output_path: Optional[str] = None,
    write_manifest: bool = False,
) -> dict:
    """Build a shot manifest; optionally write it to *output_path* as JSON.

    By default no files are written or copied — the manifest is returned in the
    result context. Set ``write_manifest=true`` (with ``output_path``) to also
    persist the JSON document.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        try:
            frame_range = [float(hou.playbar.frameRange()[0]), float(hou.playbar.frameRange()[1])]
        except Exception:  # noqa: BLE001
            frame_range = None
        try:
            fps = float(hou.fps())
        except Exception:  # noqa: BLE001
            fps = None

        cameras = _collect_typed(hou, ("cam",))
        rops = _collect_typed(hou, ("rop", "ifd", "mantra", "karma", "geometry"))
        caches = _collect_typed(hou, ("filecache", "file", "alembic", "dopio"))

        written_files = []
        for node in resolve_nodes(hou, None):
            for parm in iter_file_parms(hou, node):
                name = parm.name().lower()
                if any(tok in name for tok in ("output", "sopoutput", "picture", "lopoutput")):
                    resolved = expand_path(hou, parm.eval())
                    written_files.append(
                        {
                            "node": node.path(),
                            "parm": parm.name(),
                            "path": resolved,
                            "exists": os.path.exists(resolved),
                        }
                    )

        manifest = {
            "hip_file": (hou.hipFile.path() if hasattr(hou.hipFile, "path") else None),
            "frame_range": frame_range,
            "fps": fps,
            "cameras": cameras,
            "output_nodes": rops,
            "caches": caches,
            "written_files": written_files,
        }

        manifest_path = None
        if write_manifest:
            if not output_path:
                return skill_error(
                    "Missing output_path",
                    "write_manifest=true requires output_path",
                )
            resolved_out = os.path.expandvars(os.path.expanduser(output_path))
            os.makedirs(os.path.dirname(resolved_out) or ".", exist_ok=True)
            with open(resolved_out, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
            manifest_path = resolved_out

        return skill_success(
            "Exported shot package manifest",
            manifest=manifest,
            manifest_path=manifest_path,
            camera_count=len(cameras),
            output_node_count=len(rops),
            cache_count=len(caches),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export shot package")


@skill_entry
def main(**kwargs) -> dict:
    return export_shot_package(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
