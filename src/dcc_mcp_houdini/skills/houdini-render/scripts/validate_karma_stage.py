"""Validate known Karma stage diagnostics without modifying the USD Stage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import get_node  # noqa: E402

_FILTER_PROPERTY = "driver:parameters:aov:karma:filter"
_VBLUR_PROPERTY = "primvars:karma:object:vblur"
_RENDER_VISIBILITY_PROPERTY = "primvars:karma:object:rendervisibility"
_RENDERERS = {"karma_cpu", "karma_xpu"}
_UNSUPPORTED_FILTER_MODES = {"edge", "idcover", "ocover"}


def _diagnostic(code: str, severity: str, prim_path: str, property_name: str, fix_hint: str) -> dict:
    return {
        "code": code,
        "severity": severity,
        "prim_path": prim_path,
        "property": property_name,
        "fix_hint": fix_hint,
    }


def _authored_attribute(prim, property_name: str):
    attribute = prim.GetAttribute(property_name)
    if not attribute or not attribute.HasAuthoredValueOpinion() or attribute.Get() is None:
        return None
    return attribute


def _instance_property_sources(prim, property_name: str):
    """Yield authored property paths on one native instance and its ancestors."""
    if not prim.IsActive() or not prim.IsInstance():
        return
    current = prim
    while current:
        if _authored_attribute(current, property_name):
            yield str(current.GetPath())
        current = current.GetParent()


def _filter_entries(value):
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list) and len(parsed) == 2 and isinstance(parsed[0], str):
        return [parsed]
    if isinstance(parsed, list):
        return [entry for entry in parsed if isinstance(entry, list) and len(entry) == 2]
    return []


def _unsupported_filter_modes(value):
    modes = set()
    for name, options in _filter_entries(value):
        filter_name = str(name).lower()
        mode = str(options.get("mode", "")).lower() if isinstance(options, dict) else ""
        if filter_name in {"edge", "edgedetect"}:
            modes.add("edge")
        if mode in _UNSUPPORTED_FILTER_MODES:
            modes.add(mode)
    return sorted(modes)


def _host_version(hou):
    version = tuple(int(part) for part in hou.applicationVersion()[:3])
    if len(version) != 3:
        raise RuntimeError("Houdini did not report a complete host build")
    return version, ".".join(str(part) for part in version)


def validate_karma_stage(lop_path: str, renderer: str = "karma_xpu") -> dict:
    """Return known Karma diagnostics for a composed LOP USD Stage."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        renderer_name = str(renderer or "").lower()
        if renderer_name not in _RENDERERS:
            raise ValueError("renderer must be one of: karma_cpu, karma_xpu")

        node = get_node(hou, lop_path)
        stage_method = getattr(node, "stage", None)
        if not callable(stage_method):
            raise ValueError("Houdini node is not a LOP node: {}".format(lop_path))
        stage = stage_method()
        if stage is None:
            raise ValueError("LOP node returned no composed USD Stage: {}".format(lop_path))

        version, host_build = _host_version(hou)
        diagnostics = []
        vblur_sources = set()
        visibility_sources = set()

        for prim in stage.Traverse():
            for prim_path in _instance_property_sources(prim, _VBLUR_PROPERTY):
                if prim_path in vblur_sources:
                    continue
                vblur_sources.add(prim_path)
                diagnostics.append(
                    _diagnostic(
                        "KARMA_INSTANCE_VBLUR_PROTOTYPE_ONLY",
                        "warning",
                        prim_path,
                        _VBLUR_PROPERTY,
                        "After Scene Import, use a Render Geometry Settings LOP to block the inherited vblur "
                        "opinion and author velocity blur on the prototype instead of the native instance or ancestor.",
                    )
                )

            if version[:2] == (21, 0) and version[2] < 762:
                for prim_path in _instance_property_sources(prim, _RENDER_VISIBILITY_PROPERTY):
                    if prim_path in visibility_sources:
                        continue
                    visibility_sources.add(prim_path)
                    diagnostics.append(
                        _diagnostic(
                            "KARMA_INSTANCE_RENDERVISIBILITY_HOST_DIAGNOSTIC",
                            "info",
                            prim_path,
                            _RENDER_VISIBILITY_PROPERTY,
                            "This is the known innocuous Houdini 21.0 host diagnostic. It was removed in 21.0.762; "
                            "on older builds author the property on the prototype when practical.",
                        )
                    )

            if not prim.IsActive() or str(prim.GetTypeName()) != "RenderVar":
                continue
            attribute = _authored_attribute(prim, _FILTER_PROPERTY)
            modes = _unsupported_filter_modes(attribute.Get()) if attribute else []
            if modes:
                diagnostics.append(
                    _diagnostic(
                        "KARMA_UNSUPPORTED_RENDER_VAR_FILTER",
                        "warning",
                        str(prim.GetPath()),
                        _FILTER_PROPERTY,
                        "Replace {} with a supported filter. For PrimId, keep sourceName=ray:primid and "
                        'dataType=int while changing only the filter, for example to ["minmax",{{"mode":"min"}}] '
                        'or ["ubox",{{}}].'.format(", ".join(modes)),
                    )
                )

        return skill_success(
            "Validated Karma USD Stage",
            lop_path=str(node.path()),
            renderer=renderer_name,
            host_build=host_build,
            valid=not any(item["severity"] == "warning" for item in diagnostics),
            diagnostics=diagnostics,
        )
    except ValueError as exc:
        return skill_error("Invalid Karma stage validation request", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate Karma USD Stage")


@skill_entry
def main(**kwargs) -> dict:
    return validate_karma_stage(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
