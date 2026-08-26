"""Append a Convert SOP to change the geometry primitive type."""

from __future__ import annotations

from typing import Optional

from _mesh_common import (  # noqa: E402
    get_node,
    make_downstream_sop,
    node_summary,
    set_parm_if_exists,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

# Friendly target type -> convert SOP 'totype' menu token.
_TO_TYPE = {
    "polygons": "poly",
    "poly": "poly",
    "mesh": "mesh",
    "nurbs": "nurbs",
    "bezier": "bezier",
    "subdivision": "subdiv",
    "subdiv": "subdiv",
}


def convert_geometry(
    input_path: str,
    to_type: str = "polygons",
    node_name: Optional[str] = None,
) -> dict:
    """Create a Convert SOP downstream of *input_path* set to ``to_type``."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    token = _TO_TYPE.get(to_type.lower())
    if token is None:
        return skill_error(
            "Unsupported target type",
            "to_type must be one of: {}".format(", ".join(sorted(set(_TO_TYPE)))),
            requested=to_type,
        )
    created = None
    try:
        source = get_node(hou, input_path)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(source, "convert", node_name))
            set_parm_if_exists(created, "totype", token)
            result = skill_success(
                "Created convert SOP",
                input_path=source.path(),
                node=node_summary(created),
                to_type=token,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create convert SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return convert_geometry(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
