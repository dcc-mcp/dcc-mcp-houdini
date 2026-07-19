"""Read renderer/camera/resolution/frame-range/output from a ROP node."""

from __future__ import annotations

from _render_common import eval_first_parm, get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_OUTPUT_PARMS = ("picture", "vm_picture", "lopoutput", "sopoutput", "filename", "outputimage")


def get_render_settings(rop_path: str) -> dict:
    """Return structured render settings read from the ROP at *rop_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rop = get_node(hou, rop_path)
        res_x = eval_first_parm(rop, ("res_overridex", "resx", "vm_resx"))
        res_y = eval_first_parm(rop, ("res_overridey", "resy", "vm_resy"))
        output_frame = float(hou.frame())
        output_path = eval_first_parm(rop, _OUTPUT_PARMS)
        settings = {
            "rop": node_summary(rop),
            "renderer": rop.type().name(),
            "camera": eval_first_parm(rop, ("camera", "render_camera")),
            "resolution": [res_x, res_y] if (res_x is not None or res_y is not None) else None,
            "frame_range": eval_first_parm(rop, ("f",)),
            "output_path": output_path,
            "output_path_pattern": eval_first_parm(rop, _OUTPUT_PARMS, preserve_string=True),
            "output_path_resolution": {
                "frame": output_frame,
                "paths": output_path
                if isinstance(output_path, list)
                else ([] if output_path is None else [output_path]),
            },
            "image_format": eval_first_parm(rop, ("vm_image_format", "image_format")),
        }
        return skill_success("Read render settings", **settings)
    except Exception as exc:
        return skill_exception(exc, message="Failed to read render settings")


@skill_entry
def main(**kwargs) -> dict:
    return get_render_settings(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
