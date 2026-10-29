"""Read back and validate a Copernicus -> Unreal texture-set manifest.

Pure-Python (no ``hou``): this is the consumer-side contract check. It confirms
the sidecar manifest written by ``export_copernicus_for_unreal`` is well-formed,
re-derives the color convention for every texture, and returns the ready-to-use
Unreal import/material plans.
"""

import os
from typing import Any, Dict

import _unreal_common as common
from dcc_mcp_core.skill import run_main, skill_entry, skill_error, skill_exception, skill_success


def inspect_unreal_manifest(manifest_path: str) -> Dict[str, Any]:
    """Validate a texture-set manifest and expose its consumable plans."""
    if not isinstance(manifest_path, str) or not manifest_path:
        return skill_error("Invalid manifest path", "manifest_path must be a non-empty string")
    if not os.path.isfile(manifest_path):
        return skill_error("Manifest not found", "no file at {}".format(manifest_path))
    try:
        data = common.load_manifest(manifest_path)
        common.validate_manifest(data)
    except (ValueError, TypeError, OSError) as exc:
        return skill_exception(exc, message="Invalid Copernicus -> Unreal manifest", include_traceback=False)

    textures = data["textures"]
    return skill_success(
        "Validated Copernicus -> Unreal texture-set manifest",
        manifest_path=manifest_path,
        schema_version=data["schema_version"],
        asset_name=data["asset_name"],
        destination_path=data["destination_path"],
        texture_count=len(textures),
        import_call_count=len(data["import_plan"]),
        has_material_plan=data["material_plan"] is not None,
        import_plan=data["import_plan"],
        material_plan=data["material_plan"],
        textures=textures,
        warnings=data["warnings"],
        deferred=data.get("deferred", []),
    )


@skill_entry
def main(**kwargs):
    return inspect_unreal_manifest(**kwargs)


if __name__ == "__main__":
    run_main(main)
