"""Create a render layer / AOV pass setup in Solaris (/stage) or a ROP network."""

from __future__ import annotations

import os
from typing import Optional

from _render_common import eval_first_parm, get_node, node_summary, set_first_parm  # noqa: E402
from configure_aovs import _configure_mantra_aovs  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _normalized_output_samples(hou, output_path: str) -> set:
    frame = float(hou.frame())
    samples = set()
    for sample_frame in (frame, frame + 1.0):
        expanded = hou.text.expandStringAtFrame(output_path, sample_frame)
        absolute = hou.text.abspath(expanded)
        samples.add(os.path.normcase(os.path.normpath(hou.text.normpath(absolute))))
    return samples


def create_render_layer(
    name: str,
    parent_path: str = "/stage",
    aovs: Optional[list] = None,
    purpose: str = "beauty",
    source_rop_path: Optional[str] = None,
    output_path: Optional[str] = None,
    candidate_objects: Optional[str] = None,
    force_objects: Optional[str] = None,
    matte_objects: Optional[str] = None,
    exclude_objects: Optional[str] = None,
    phantom_objects: Optional[str] = None,
) -> dict:
    """Create a render layer (RenderVar / RenderProduct) under *parent_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        is_solaris = parent_path.startswith("/stage")

        if is_solaris:
            # Solaris: create a Render Product LOP
            layer = parent.createNode("renderproduct", node_name=name)
            set_first_parm(layer, ("productname",), name)
            if purpose:
                set_first_parm(layer, ("producttype",), purpose)
            # Create render vars (AOVs) as children
            created_aovs = []
            if aovs:
                for aov_name in aovs:
                    rv = layer.createNode("rendervar", node_name=aov_name)
                    set_first_parm(rv, ("sourceName", "sourcename"), aov_name)
                    set_first_parm(rv, ("sourceType", "sourcetype"), "raw")
                    created_aovs.append({"name": aov_name, "path": rv.path()})
            return skill_success(
                "Created render layer (Solaris)",
                node=node_summary(layer),
                purpose=purpose,
                aovs=created_aovs,
                context="solaris",
            )

        if not source_rop_path:
            return skill_error(
                "Missing source_rop_path",
                "source_rop_path is required when creating a traditional ROP render layer",
            )
        if not output_path or not output_path.strip():
            return skill_error(
                "Missing output_path",
                "output_path is required so the cloned ROP cannot overwrite its source output",
            )
        if not name or "/" in name or "\\" in name:
            return skill_error("Invalid layer name", "name must be a non-empty Houdini node name")
        if parent.node(name) is not None:
            return skill_error(
                "Render layer already exists",
                "A node named '{}' already exists under '{}'".format(name, parent_path),
            )

        source = get_node(hou, source_rop_path)
        source_type = source.type().name().split("::", 1)[0]
        if source_type != "ifd":
            return skill_error(
                "Unsupported source ROP",
                "source_rop_path must reference a Mantra ifd ROP",
                source_rop_path=source_rop_path,
                source_type=source_type,
            )
        source_output = eval_first_parm(source, ("vm_picture",), preserve_string=True)
        if source_output is not None and _normalized_output_samples(hou, output_path) & _normalized_output_samples(
            hou, str(source_output)
        ):
            return skill_error(
                "Output path is not dedicated",
                "output_path must differ from the source Mantra ROP output",
                source_rop_path=source_rop_path,
                output_path=output_path,
            )

        layer = source.copyTo(parent)
        try:
            layer.setName(name, unique_name=False)
            requested_parms = {
                "vm_picture": output_path,
                "vobject": candidate_objects,
                "forceobject": force_objects,
                "matte_objects": matte_objects,
                "excludeobject": exclude_objects,
                "phantom_objects": phantom_objects,
            }
            missing = [
                parm_name
                for parm_name, value in requested_parms.items()
                if value is not None and set_first_parm(layer, (parm_name,), value) is None
            ]
            if missing:
                raise ValueError("Cloned Mantra ROP is missing required parameters: {}".format(", ".join(missing)))

            configured_aovs = []
            unsupported_aovs = []
            if aovs:
                configured_aovs, unsupported_aovs = _configure_mantra_aovs(layer, aovs, "add")
                if unsupported_aovs:
                    raise ValueError(
                        "Unsupported Mantra AOVs: {}".format(", ".join(str(name) for name in unsupported_aovs))
                    )
            return skill_success(
                "Created render layer (Mantra ROP)",
                node=node_summary(layer),
                purpose=purpose,
                context="rop",
                source_rop_path=source_rop_path,
                output_path=output_path,
                masks={
                    key: value for key, value in requested_parms.items() if key != "vm_picture" and value is not None
                },
                aovs=configured_aovs,
                unsupported_aovs=unsupported_aovs,
            )
        except Exception:
            destroy = getattr(layer, "destroy", None)
            if callable(destroy):
                destroy()
            raise
    except Exception as exc:
        return skill_exception(exc, message="Failed to create render layer")


@skill_entry
def main(**kwargs) -> dict:
    return create_render_layer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
