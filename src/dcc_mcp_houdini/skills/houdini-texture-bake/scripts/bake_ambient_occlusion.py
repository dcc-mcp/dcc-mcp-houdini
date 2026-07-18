"""Bake ambient occlusion to a texture via Labs Maps Baker, Bake Texture ROP, or COP fallback."""

from __future__ import annotations

import os
from typing import List, Optional

from _texture_bake_common import (  # noqa: E402
    collect_geometry,
    create_or_get_bake_rop,
    detect_bake_methods,
    node_summary,
    set_parm_if_exists,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _bake_ao_via_rop(
    hou, rop, objects: List[str], output_path: str, resolution: List[int], samples: int, max_distance: float
) -> dict:
    """Configure and execute a Bake Texture ROP for ambient occlusion."""
    obj_str = " ".join(objects)

    set_parm_if_exists(rop, "soppath", obj_str) or set_parm_if_exists(rop, "objects", obj_str)
    set_parm_if_exists(rop, "picture", output_path)
    set_parm_if_exists(rop, "resolution", resolution)
    set_parm_if_exists(rop, "res1", resolution[0])
    set_parm_if_exists(rop, "res2", resolution[1])
    set_parm_if_exists(rop, "samples", samples)
    set_parm_if_exists(rop, "maxdist", max_distance)
    set_parm_if_exists(rop, "aomap", True)
    set_parm_if_exists(rop, "bake_aomap", True)

    try:
        rop.render(verbose=False)
    except TypeError:
        rop.render()

    written = [output_path] if os.path.isfile(output_path) else []

    return skill_success(
        "Baked ambient occlusion via Bake Texture ROP",
        bake_method="bake_texture_rop",
        written_files=written,
        output_path=output_path,
        resolution=resolution,
        samples=samples,
        max_distance=max_distance,
        rop=node_summary(hou, rop.path()),
        objects=objects,
        prompt="Use bake_lighting for full lighting bake or bake_textures for multi-map baking.",
    )


def _bake_ao_via_labs(
    hou, objects: List[str], output_path: str, resolution: List[int], samples: int, max_distance: float
) -> dict:
    """Bake AO using Labs Maps Baker node."""
    parent = hou.node("/out")
    if parent is None:
        return skill_error("No /out context", "Cannot create bake nodes")

    baker = parent.createNode("maps_baker", "_tmp_bake_ao_labs")
    try:
        obj_str = " ".join(objects)
        set_parm_if_exists(baker, "soppath", obj_str) or set_parm_if_exists(baker, "objects", obj_str)
        set_parm_if_exists(baker, "picture", output_path)
        set_parm_if_exists(baker, "resolution", resolution)
        set_parm_if_exists(baker, "samples", samples)
        set_parm_if_exists(baker, "maxdist", max_distance)
        set_parm_if_exists(baker, "ao", True)
        set_parm_if_exists(baker, "bake_ambient_occlusion", True)

        try:
            baker.render(verbose=False)
        except TypeError:
            baker.render()

        written = [output_path] if os.path.isfile(output_path) else []

        return skill_success(
            "Baked ambient occlusion via Labs Maps Baker",
            bake_method="labs_maps_baker",
            written_files=written,
            output_path=output_path,
            resolution=resolution,
            samples=samples,
            max_distance=max_distance,
            objects=objects,
        )
    finally:
        try:
            baker.destroy()
        except Exception:
            pass


def _bake_ao_via_cop(hou, objects: List[str], output_path: str, resolution: List[int], samples: int) -> dict:
    """Bake AO using a COP network as last-resort fallback.

    Creates an occlusion COP, attaches geometry, and renders a single frame.
    """
    cop_net = hou.node("/img")
    if cop_net is None:
        cop_net = hou.node("/").createNode("img", "img")
    cop_net = hou.node("/img")

    ao_cop = cop_net.createNode("occlusion", "_tmp_bake_ao_cop")
    try:
        obj_str = " ".join(objects)
        set_parm_if_exists(ao_cop, "soppath", obj_str) or set_parm_if_exists(ao_cop, "objects", obj_str)
        set_parm_if_exists(ao_cop, "samples", samples)
        set_parm_if_exists(ao_cop, "resolution", resolution)

        rop = cop_net.createNode("rop_cop2", "_tmp_bake_ao_rop")
        rop.setInput(0, ao_cop)
        set_parm_if_exists(rop, "copoutput", output_path)
        set_parm_if_exists(rop, "trange", 0)

        try:
            rop.render(verbose=False)
        except TypeError:
            rop.render()

        written = [output_path] if os.path.isfile(output_path) else []

        return skill_success(
            "Baked ambient occlusion via COP fallback",
            bake_method="cop_fallback",
            written_files=written,
            output_path=output_path,
            resolution=resolution,
            samples=samples,
            objects=objects,
            warnings=["COP-based bake is limited; consider installing sidefx_labs for Labs Maps Baker."],
        )
    finally:
        try:
            ao_cop.destroy()
        except Exception:
            pass
        try:
            rop.destroy()
        except Exception:
            pass


def bake_ambient_occlusion(
    rop_path: str = "/out/bake_ao",
    objects: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    resolution: Optional[List[int]] = None,
    samples: int = 64,
    max_distance: float = 0.0,
) -> dict:
    """Bake ambient occlusion to a texture file."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        methods = detect_bake_methods(hou)
        geo = collect_geometry(hou, objects)

        if not geo:
            return skill_error(
                "No geometry found",
                "Provide 'objects' or ensure renderable OBJ nodes exist",
                available_methods=methods["available_methods"],
            )

        res = resolution or [1024, 1024]
        out = output_path or "$HIP/ao.$F4.exr"

        if methods["labs_maps_baker_available"]:
            return _bake_ao_via_labs(hou, geo, out, res, samples, max_distance)

        if methods["bake_texture_rop_available"]:
            try:
                rop = create_or_get_bake_rop(hou, rop_path)
                return _bake_ao_via_rop(hou, rop, geo, out, res, samples, max_distance)
            except Exception as exc:
                return skill_error(
                    "Failed to create Bake Texture ROP",
                    str(exc),
                    available_methods=methods["available_methods"],
                    recommendations=methods["recommendations"],
                )

        # COP fallback
        return _bake_ao_via_cop(hou, geo, out, res, samples)

    except Exception as exc:
        return skill_exception(exc, message="Failed to bake ambient occlusion")


@skill_entry
def main(**kwargs) -> dict:
    return bake_ambient_occlusion(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
