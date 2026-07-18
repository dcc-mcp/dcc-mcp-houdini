"""Read bounded attribute values from one USD prim."""

from __future__ import annotations

from typing import Optional

from _usd_common import (  # noqa: E402
    bounded_value,
    make_time_code,
    require_range,
    resolve_prim,
    resolve_stage,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_prim_attributes(
    lop_node_path: str,
    prim_path: str,
    name_filter: Optional[str] = None,
    time_code: Optional[float] = None,
    max_attributes: int = 50,
    max_value_items: int = 64,
    max_value_chars: int = 1024,
) -> dict:
    """Return filtered USD attributes within explicit payload bounds."""
    try:
        import hou  # noqa: PLC0415
        from pxr import Usd  # noqa: PLC0415
    except ImportError as exc:
        return skill_error("Houdini USD APIs not available", str(exc))

    try:
        require_range(max_attributes, "max_attributes", 1, 100)
        require_range(max_value_items, "max_value_items", 1, 256)
        require_range(max_value_chars, "max_value_chars", 64, 4096)
        if name_filter is not None and len(str(name_filter)) > 128:
            raise ValueError("name_filter must be at most 128 characters")
        node, stage = resolve_stage(hou, lop_node_path)
        prim = resolve_prim(stage, prim_path)
        usd_time = make_time_code(Usd, time_code)
        lowered_filter = str(name_filter).lower() if name_filter else None
        matching = sorted(
            (
                attribute
                for attribute in prim.GetAttributes()
                if lowered_filter is None or lowered_filter in str(attribute.GetName()).lower()
            ),
            key=lambda attribute: str(attribute.GetName()),
        )

        records = []
        value_truncated_count = 0
        for attribute in matching[:max_attributes]:
            value = bounded_value(attribute.Get(usd_time), max_value_items, max_value_chars)
            if value["truncated"]:
                value_truncated_count += 1
            record = {
                "name": str(attribute.GetName()),
                "type_name": str(attribute.GetTypeName()),
                "authored": bool(attribute.HasAuthoredValueOpinion()),
            }
            record.update(value)
            records.append(record)

        return skill_success(
            "Read USD prim attributes",
            lop_node_path=str(node.path()),
            prim_path=str(prim.GetPath()),
            time_code="default" if time_code is None else float(time_code),
            name_filter=name_filter,
            attributes=records,
            matched_count=len(matching),
            returned_count=len(records),
            truncated=len(matching) > len(records) or value_truncated_count > 0,
            attribute_list_truncated=len(matching) > len(records),
            value_truncated_count=value_truncated_count,
            bounds={
                "max_attributes": max_attributes,
                "max_value_items": max_value_items,
                "max_value_chars": max_value_chars,
            },
        )
    except ValueError as exc:
        return skill_error("Invalid USD attribute query", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to read USD prim attributes")


@skill_entry
def main(**kwargs) -> dict:
    return get_prim_attributes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
