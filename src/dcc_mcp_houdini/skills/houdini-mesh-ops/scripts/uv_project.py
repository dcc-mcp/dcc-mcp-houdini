"""Project UVs through a verified native UV Project SOP."""

from __future__ import annotations

import re
from typing import Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_menu_parm,
    set_scalar_parm_verified,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_ATTRIBUTE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROJECTION_LABELS = {
    "planar": ("orthographic", "planar"),
    "cylindrical": ("cylindrical", "cylinder"),
    "spherical": ("spherical", "sphere"),
}


def uv_project(
    input_path: str,
    projection: str = "planar",
    group: Optional[str] = None,
    uv_attribute: str = "uv",
    node_name: Optional[str] = None,
) -> dict:
    """Append UV Project and verify the requested vertex UV attribute exists."""
    if not isinstance(input_path, str) or not input_path:
        return skill_error("Invalid input", "input_path must be a non-empty node path")
    if projection not in _PROJECTION_LABELS:
        return skill_error("Invalid UV projection", "projection must be planar, cylindrical, or spherical")
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

    created = None
    try:
        source = get_node(hou, input_path)
        before = geometry_readback(source)
        created = make_downstream_sop(source, "uvproject", node_name)
        set_scalar_parm_verified(created, ("uvattrib",), uv_attribute, ("UV Attribute",))
        if group is not None:
            set_scalar_parm_verified(created, ("group",), group, ("Group",))
        token = set_menu_parm(created, "projection", _PROJECTION_LABELS[projection])
        readback = cook_readback(created, before=before, require_change=False)
        geometry = created.geometry()
        if geometry.findVertexAttrib(uv_attribute) is None:
            raise RuntimeError("UV Project did not create vertex attribute: {}".format(uv_attribute))
        readback["uv_attribute"] = uv_attribute
        return skill_success(
            "Created and verified UV Project SOP",
            input_path=source.path(),
            node=node_summary(created),
            parameters={
                "group": group or "",
                "projection": projection,
                "projection_token": token,
                "uv_attribute": uv_attribute,
            },
            readback=readback,
        )
    except Exception as exc:
        if created is not None:
            try:
                created.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(exc, message="Failed to create verified UV Project SOP")


@skill_entry
def main(**kwargs) -> dict:
    return uv_project(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
