"""Generate UVs through a verified native UV Unwrap SOP."""

from __future__ import annotations

import re
from typing import Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_scalar_parm_verified,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

_ATTRIBUTE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def auto_uv(
    input_path: str,
    group: Optional[str] = None,
    uv_attribute: str = "uv",
    node_name: Optional[str] = None,
) -> dict:
    """Append UV Unwrap and verify the requested vertex UV attribute exists."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty node path")
    if group is not None and (not isinstance(group, str) or not group.strip()):
        return skill_error("Invalid UV group", "group must be a non-empty selection when provided")
    if not isinstance(uv_attribute, str) or not _ATTRIBUTE_NAME.fullmatch(uv_attribute):
        return skill_error("Invalid UV attribute", "uv_attribute must be a valid Houdini attribute name")
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        source = get_node(hou, input_path)
        before = geometry_readback(source)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "uvunwrap", node_name))
            set_scalar_parm_verified(created, ("uvattrib",), uv_attribute, ("UV Attribute",))
            if group is not None:
                set_scalar_parm_verified(created, ("group",), group, ("Group",))
            readback = cook_readback(created, before=before, require_change=False)
            geometry = created.geometry()
            if geometry.findVertexAttrib(uv_attribute) is None:
                raise RuntimeError("UV Unwrap did not create the requested vertex attribute")
            readback["uv_attribute"] = uv_attribute
            result = skill_success(
                "Created and verified UV Unwrap SOP",
                input_path=source.path(),
                node=node_summary(created),
                parameters={"group": group or "", "uv_attribute": uv_attribute},
                readback=readback,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create verified UV Unwrap SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return auto_uv(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
