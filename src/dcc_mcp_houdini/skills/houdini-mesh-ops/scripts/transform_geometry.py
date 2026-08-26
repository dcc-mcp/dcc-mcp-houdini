"""Append a Transform (xform) SOP to translate/rotate/scale geometry."""

from __future__ import annotations

from typing import List, Optional

from _mesh_common import (  # noqa: E402
    get_node,
    make_downstream_sop,
    node_summary,
    set_parm_if_exists,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def transform_geometry(
    input_path: str,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    node_name: Optional[str] = None,
) -> dict:
    """Create a Transform SOP downstream of *input_path* and set t/r/s."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = None
    try:
        source = get_node(hou, input_path)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "xform", node_name))
            applied = {}
            if translate is not None and set_parm_if_exists(created, "t", translate):
                applied["t"] = list(translate)
            if rotate is not None and set_parm_if_exists(created, "r", rotate):
                applied["r"] = list(rotate)
            if scale is not None and set_parm_if_exists(created, "s", scale):
                applied["s"] = list(scale)
            result = skill_success(
                "Created transform SOP",
                input_path=source.path(),
                node=node_summary(created),
                applied=applied,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create transform SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return transform_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
