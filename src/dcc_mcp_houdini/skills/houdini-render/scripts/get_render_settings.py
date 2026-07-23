"""Read renderer/camera/resolution/frame-range/output from a ROP node."""

from __future__ import annotations

from _render_common import (  # noqa: E402
    PRIMARY_OUTPUT_PARMS,
    eval_first_parm,
    eval_first_parm_named,
    get_node,
    node_summary,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)) or hasattr(value, "__iter__"):
        try:
            return [_json_value(item) for item in value]
        except TypeError:
            pass
    return str(value)


def _usd_value(prim, name):
    attribute = prim.GetAttribute(name)
    return _json_value(attribute.Get()) if attribute else None


def _usd_targets(prim, name):
    relationship = prim.GetRelationship(name)
    return list(relationship.GetTargets()) if relationship else []


def _render_settings_prim(stage):
    path = stage.GetMetadata("renderSettingsPrimPath")
    if path:
        prim = stage.GetPrimAtPath(path)
        if prim:
            return prim
    return next((prim for prim in stage.Traverse() if str(prim.GetTypeName()) == "RenderSettings"), None)


def _solaris_settings(hou, rop):
    loppath = eval_first_parm(rop, ("loppath",))
    lop = hou.node(loppath) if loppath else None
    if lop is None:
        inputs = getattr(rop, "inputs", None)
        lop = (
            next((node for node in inputs() if callable(getattr(node, "stage", None))), None)
            if callable(inputs)
            else None
        )
    if lop is None or not callable(getattr(lop, "stage", None)):
        raise ValueError("USD Render ROP has no resolvable LOP stage")

    stage = lop.stage()
    settings = _render_settings_prim(stage) if stage is not None else None
    if settings is None:
        raise ValueError("LOP stage has no active RenderSettings prim")

    settings_camera = next((str(path) for path in _usd_targets(settings, "camera")), None)
    settings_resolution = _usd_value(settings, "resolution")
    product_paths = _usd_targets(settings, "products")
    products = []
    aovs = []
    for product_path in product_paths:
        product = stage.GetPrimAtPath(product_path)
        if not product:
            continue
        var_paths = _usd_targets(product, "orderedVars")
        product_aovs = []
        for var_path in var_paths:
            render_var = stage.GetPrimAtPath(var_path)
            if not render_var:
                continue
            summary = {
                "path": str(var_path),
                "source_name": _usd_value(render_var, "sourceName"),
                "source_type": _usd_value(render_var, "sourceType"),
                "data_type": _usd_value(render_var, "dataType"),
            }
            product_aovs.append(summary)
            aovs.append(summary)
        product_camera = next((str(path) for path in _usd_targets(product, "camera")), None)
        products.append(
            {
                "path": str(product_path),
                "output_path": _usd_value(product, "productName"),
                "camera": product_camera or settings_camera,
                "resolution": _usd_value(product, "resolution") or settings_resolution,
                "aovs": product_aovs,
            }
        )

    primary = products[0] if products else {}
    camera = primary.get("camera") or settings_camera
    resolution = primary.get("resolution") or settings_resolution
    output_patterns = [product["output_path"] for product in products if product.get("output_path")]
    attributes = {
        str(attribute.GetName()): _json_value(attribute.Get())
        for attribute in settings.GetAttributes()
        if "sample" in str(attribute.GetName()).lower()
    }
    delegate = eval_first_parm(rop, ("renderer", "renderdelegate", "delegate"))
    if delegate in (None, "", "default"):
        delegate = _usd_value(settings, "husk:default_delegate")
    engine = _usd_value(settings, "karma:global:engine") or _usd_value(settings, "karma:global:renderengine")
    frame_range = eval_first_parm(rop, ("f",)) or [float(hou.frame()), float(hou.frame()), 1.0]
    renderer = "karma" if engine is not None else delegate
    unresolved = [
        name
        for name, value in (
            ("camera", camera),
            ("resolution", resolution),
            ("output_path", output_patterns),
            ("renderer", renderer),
            ("delegate", delegate),
            ("samples", attributes),
            ("aovs", aovs),
        )
        if not value
    ]
    resolved_paths = [
        hou.text.expandStringAtFrame(pattern, float(hou.frame()))
        if "$F" in str(pattern) and callable(getattr(hou.text, "expandStringAtFrame", None))
        else pattern
        for pattern in output_patterns
    ]
    intermediate_name, intermediate_pattern = eval_first_parm_named(rop, ("lopoutput",), preserve_string=True)
    return {
        "rop": node_summary(rop),
        "renderer": renderer or rop.type().name(),
        "delegate": delegate,
        "engine": engine,
        "camera": camera,
        "resolution": list(resolution) if resolution is not None else None,
        "frame_range": list(frame_range),
        "output_parm_name": "productName" if output_patterns else None,
        "output_path": resolved_paths,
        "output_path_pattern": output_patterns,
        "output_path_resolution": {"frame": float(hou.frame()), "paths": resolved_paths},
        "intermediate_usd": {
            "parm_name": intermediate_name,
            "path": eval_first_parm(rop, ("lopoutput",)),
            "path_pattern": intermediate_pattern,
        },
        "render_settings_prim": str(settings.GetPath()),
        "render_products": products,
        "samples": attributes,
        "aovs": aovs,
        "image_format": None,
        "unresolved": unresolved,
        "unsupported": [],
    }


def get_render_settings(rop_path: str) -> dict:
    """Return structured render settings read from the ROP at *rop_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rop = get_node(hou, rop_path)
        solaris_error = None
        if rop.type().name().split("::", 1)[0] == "usdrender_rop":
            try:
                return skill_success("Read effective Solaris render settings", **_solaris_settings(hou, rop))
            except ValueError as exc:
                solaris_error = str(exc)
        res_x = eval_first_parm(rop, ("res_overridex", "resx", "vm_resx"))
        res_y = eval_first_parm(rop, ("res_overridey", "resy", "vm_resy"))
        output_frame = float(hou.frame())
        output_parms = (
            tuple(name for name in PRIMARY_OUTPUT_PARMS if name != "lopoutput")
            if solaris_error
            else PRIMARY_OUTPUT_PARMS
        )
        output_parm_name, output_path_pattern = eval_first_parm_named(rop, output_parms, preserve_string=True)
        output_path = eval_first_parm(rop, (output_parm_name,)) if output_parm_name else None
        settings = {
            "rop": node_summary(rop),
            "renderer": rop.type().name(),
            "camera": eval_first_parm(rop, ("camera", "render_camera")),
            "resolution": [res_x, res_y] if (res_x is not None or res_y is not None) else None,
            "frame_range": eval_first_parm(rop, ("f",)),
            "output_parm_name": output_parm_name,
            "output_path": output_path,
            "output_path_pattern": output_path_pattern,
            "output_path_resolution": {
                "frame": output_frame,
                "paths": output_path
                if isinstance(output_path, list)
                else ([] if output_path is None else [output_path]),
            },
            "image_format": eval_first_parm(rop, ("vm_image_format", "image_format")),
        }
        if solaris_error:
            settings.update(
                intermediate_usd={
                    "parm_name": "lopoutput",
                    "path": eval_first_parm(rop, ("lopoutput",)),
                    "path_pattern": eval_first_parm_named(rop, ("lopoutput",), preserve_string=True)[1],
                },
                unresolved=["effective_solaris_stage"],
                unsupported=[],
                warnings=[solaris_error],
            )
        return skill_success("Read render settings", **settings)
    except Exception as exc:
        return skill_exception(exc, message="Failed to read render settings")


@skill_entry
def main(**kwargs) -> dict:
    return get_render_settings(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
