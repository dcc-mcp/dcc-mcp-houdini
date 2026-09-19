"""Set USD attributes on a stage prim with readback."""

from __future__ import annotations

from typing import Any

from _usd_common import make_time_code, require_absolute_path, resolve_prim, resolve_stage
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

MAX_ATTRIBUTES = 32


def _is_number(item: Any) -> bool:
    return isinstance(item, (int, float)) and not isinstance(item, bool)


def _typed_value(Gf: Any, Sdf: Any, value: Any):
    """Return ``(sdf_type, usd_value)`` for *value*, or ``None`` when unsupported.

    OpenUSD maps Float2 and Float3 onto ``Gf.Vec2f`` and ``Gf.Vec3f``. Handing it
    a raw Python list instead raises an ArgumentError inside ``Set``, so vector
    values are converted here rather than at the call site.
    """
    if isinstance(value, bool):
        return Sdf.ValueTypeNames.Bool, value
    if isinstance(value, int):
        return Sdf.ValueTypeNames.Int, value
    if isinstance(value, float):
        return Sdf.ValueTypeNames.Float, value
    if isinstance(value, str):
        return Sdf.ValueTypeNames.String, value
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and all(_is_number(item) for item in value):
            return Sdf.ValueTypeNames.Float3, Gf.Vec3f(*(float(item) for item in value))
        if len(value) == 2 and all(_is_number(item) for item in value):
            return Sdf.ValueTypeNames.Float2, Gf.Vec2f(*(float(item) for item in value))
    return None


def _remove_properties(prim: Any, names) -> None:
    """Remove *names* from *prim*, ignoring failures so cleanup cannot throw."""
    for name in names:
        try:
            prim.RemoveProperty(name)
        except Exception:
            pass


def set_prim_attributes(lop_node_path: str, prim_path: str, attributes: dict, time_code=None) -> dict:
    try:
        import hou
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        from pxr import Gf, Sdf, Usd  # noqa: PLC0415
    except ImportError:
        return skill_error("USD not available", "pxr.Gf, pxr.Sdf and pxr.Usd could not be imported")
    try:
        if not isinstance(attributes, dict) or not attributes:
            raise ValueError("attributes must be a non-empty object")
        if len(attributes) > MAX_ATTRIBUTES:
            raise ValueError("attributes must contain at most {} entries".format(MAX_ATTRIBUTES))
        require_absolute_path(prim_path, "prim_path")
        _node, stage = resolve_stage(hou, lop_node_path)
        prim = resolve_prim(stage, prim_path)
        time = make_time_code(Usd, time_code)

        # Pre-validate every entry before writing anything: validating inside the
        # write loop would leave the earlier attributes on the stage and then
        # fail, which is a partial write the caller cannot undo.
        planned = {}
        for name, value in attributes.items():
            if not str(name).replace(":", "_").replace("_", "").isalnum():
                raise ValueError("Invalid USD attribute name: {}".format(name))
            typed = _typed_value(Gf, Sdf, value)
            if typed is None:
                raise ValueError("Unsupported value type for attribute: {}".format(name))
            planned[str(name)] = typed

        applied, skipped = {}, []
        created = []
        try:
            for name, (type_name, usd_value) in planned.items():
                attribute = prim.CreateAttribute(name, type_name)
                created.append(name)
                if not attribute.Set(usd_value, time):
                    # A refused write must not leave an attribute that exists
                    # with a default value: that reads as "written" to a caller
                    # who only checks that the name is there. Only this one goes;
                    # the writes that did succeed stay.
                    skipped.append(name)
                    created.remove(name)
                    _remove_properties(prim, [name])
                    continue
                applied[name] = usd_value
        except BaseException:
            # Pre-validation cannot cover everything USD rejects at Set time, and
            # an exception here would otherwise leave the earlier writes in place.
            _remove_properties(prim, reversed(created))
            raise

        readback = {}
        for name in applied:
            attribute = prim.GetAttribute(name)
            if attribute is not None:
                readback[name] = attribute.Get(time)

        return skill_success(
            "Set USD prim attributes",
            lop_node_path=lop_node_path,
            prim_path=prim_path,
            skipped_parameters=skipped,
            applied_attributes=applied,
            attribute_readback=readback,
            readback_matches=readback == applied,
            validation_scope="stage_write_and_readback",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set USD prim attributes")


@skill_entry
def main(**kwargs):
    return set_prim_attributes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
