"""Set USD attributes on a stage prim with readback."""

from __future__ import annotations

from typing import Any

from _usd_common import make_time_code, require_absolute_path, resolve_prim, resolve_stage
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

MAX_ATTRIBUTES = 32


def _value_type(Usd: Any, Sdf: Any, value: Any) -> Any:
    """Map a JSON value to the matching Sdf type, or ``None`` when unsupported."""
    if isinstance(value, bool):
        return Sdf.ValueTypeNames.Bool
    if isinstance(value, int):
        return Sdf.ValueTypeNames.Int
    if isinstance(value, float):
        return Sdf.ValueTypeNames.Float
    if isinstance(value, str):
        return Sdf.ValueTypeNames.String
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            return Sdf.ValueTypeNames.Float3
        if len(value) == 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            return Sdf.ValueTypeNames.Float2
    return None


def set_prim_attributes(lop_node_path: str, prim_path: str, attributes: dict, time_code=None) -> dict:
    try:
        import hou
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        import Sdf  # noqa: PLC0415
        import Usd  # noqa: PLC0415
    except ImportError:
        return skill_error("USD not available", "Sdf and Usd could not be imported")
    try:
        if not isinstance(attributes, dict) or not attributes:
            raise ValueError("attributes must be a non-empty object")
        if len(attributes) > MAX_ATTRIBUTES:
            raise ValueError("attributes must contain at most {} entries".format(MAX_ATTRIBUTES))
        require_absolute_path(prim_path, "prim_path")
        _node, stage = resolve_stage(hou, lop_node_path)
        prim = resolve_prim(stage, prim_path)
        time = make_time_code(Usd, time_code)

        applied, skipped, unsupported = {}, [], []
        for name, value in attributes.items():
            if not str(name).replace(":", "_").replace("_", "").isalnum():
                raise ValueError("Invalid USD attribute name: {}".format(name))
            type_name = _value_type(Usd, Sdf, value)
            if type_name is None:
                unsupported.append(name)
                continue
            attribute = prim.CreateAttribute(str(name), type_name)
            if not attribute.Set(value, time):
                skipped.append(name)
                continue
            applied[name] = value

        readback = {}
        for name in applied:
            attribute = prim.GetAttribute(name)
            if attribute is not None:
                readback[name] = attribute.Get(time)

        if unsupported:
            raise ValueError("Unsupported attribute value types: {}".format(", ".join(sorted(unsupported))))
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
