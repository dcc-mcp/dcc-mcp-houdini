"""Bake scene lighting via Mantra or Karma render-to-texture."""

from __future__ import annotations

import os
from typing import List, Optional

from _texture_bake_common import (  # noqa: E402
    collect_geometry,
    create_or_get_bake_rop,
    node_summary,
    set_parm_if_exists,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_VALID_RENDERERS = ("mantra", "karma")


def _bake_lighting_via_rop(
    hou,
    rop,
    objects: List[str],
    camera: Optional[str],
    output_path: str,
    resolution: List[int],
    samples: int,
    renderer: str,
    bake_shadows: bool,
) -> dict:
    """Configure and execute a Bake Texture ROP for lighting."""
    obj_str = " ".join(objects)

    set_parm_if_exists(rop, "soppath", obj_str) or set_parm_if_exists(rop, "objects", obj_str)
    set_parm_if_exists(rop, "picture", output_path)
    set_parm_if_exists(rop, "resolution", resolution)
    set_parm_if_exists(rop, "res1", resolution[0])
    set_parm_if_exists(rop, "res2", resolution[1])
    set_parm_if_exists(rop, "vm_samples", samples)
    set_parm_if_exists(rop, "lighting", True)
    set_parm_if_exists(rop, "bake_lighting", True)
    set_parm_if_exists(rop, "shadows", bake_shadows)

    if camera:
        set_parm_if_exists(rop, "camera", camera)

    # Select renderer by toggling ROP parameters
    if renderer == "karma":
        set_parm_if_exists(rop, "renderer", "karma")
        set_parm_if_exists(rop, "candidate_renderer", "karma")

    try:
        rop.render(verbose=False)
    except TypeError:
        rop.render()

    written = [output_path] if os.path.isfile(output_path) else []

    return skill_success(
        "Baked lighting via {}".format(renderer),
        bake_method="bake_texture_rop",
        renderer=renderer,
        written_files=written,
        output_path=output_path,
        resolution=resolution,
        rop=node_summary(hou, rop.path()),
        objects=objects,
        camera=camera,
        bake_shadows=bake_shadows,
        prompt="Use bake_ambient_occlusion for AO or transfer_maps for normal maps.",
    )


def bake_lighting(
    rop_path: str = "/out/bake_lighting",
    camera: Optional[str] = None,
    objects: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    resolution: Optional[List[int]] = None,
    samples: int = 4,
    renderer: str = "mantra",
    bake_shadows: bool = True,
) -> dict:
    """Bake full scene lighting (diffuse + shadows) to a texture."""
    if renderer not in _VALID_RENDERERS:
        return skill_error(
            "Invalid renderer: {}".format(renderer),
            "Use one of: {}".format(", ".join(_VALID_RENDERERS)),
        )

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        geo = collect_geometry(hou, objects)
        if not geo:
            return skill_error(
                "No geometry found",
                "Provide 'objects' or ensure renderable OBJ nodes exist",
            )

        res = resolution or [1024, 1024]
        out = output_path or "$HIP/lighting.$F4.exr"

        rop = create_or_get_bake_rop(hou, rop_path)
        return _bake_lighting_via_rop(
            hou,
            rop,
            geo,
            camera,
            out,
            res,
            samples,
            renderer,
            bake_shadows,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to bake lighting")


@skill_entry
def main(**kwargs) -> dict:
    return bake_lighting(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
