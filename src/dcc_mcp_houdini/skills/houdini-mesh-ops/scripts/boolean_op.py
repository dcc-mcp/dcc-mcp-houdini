"""Combine two SOP streams through a verified native Boolean SOP."""

from __future__ import annotations

from typing import Optional

from _mesh_common import (  # noqa: E402
    cook_readback,
    geometry_readback,
    get_node,
    make_downstream_sop,
    node_summary,
    set_menu_parm_candidates,
    sop_node_transaction,
    sop_transaction_error,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

_OPERATION_LABELS = {
    "union": ("union",),
    "intersect": ("intersect", "intersection"),
    "subtract": ("a minus b", "a-b", "subtract", "a subtract b"),
}


def boolean_op(
    input_a: str,
    input_b: str,
    operation: str,
    node_name: Optional[str] = None,
) -> dict:
    """Apply a typed Boolean operation and verify its cooked result."""
    if not isinstance(input_a, str) or not input_a:
        return skill_error("Invalid Boolean input", "input_a must be a non-empty node path")
    if not isinstance(input_b, str) or not input_b:
        return skill_error("Invalid Boolean input", "input_b must be a non-empty node path")
    if input_a == input_b:
        return skill_error("Invalid Boolean inputs", "input_a and input_b must be different nodes")
    if operation not in _OPERATION_LABELS:
        return skill_error(
            "Unsupported Boolean operation",
            "operation must be one of: intersect, subtract, union",
        )
    if node_name is not None and (not isinstance(node_name, str) or not node_name):
        return skill_error("Invalid node name", "node_name must be a non-empty string when provided")

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        left = get_node(hou, input_a)
        right = get_node(hou, input_b)
        if left.parent() is None or right.parent() is not left.parent():
            raise ValueError("Boolean inputs must share one parent SOP network")
        before = geometry_readback(left)
        with sop_node_transaction() as transaction:
            created = transaction.own(make_downstream_sop(left, "boolean", node_name))
            created.setInput(1, right)
            token = set_menu_parm_candidates(
                created,
                ("booleanop", "operation"),
                _OPERATION_LABELS[operation],
                ("Operation",),
            )
            readback = cook_readback(created, before=before)
            result = skill_success(
                "Created and verified Boolean SOP",
                inputs=[left.path(), right.path()],
                node=node_summary(created),
                parameters={"operation": operation, "operation_token": token},
                readback=readback,
            )
            transaction.commit()
        return result
    except Exception as exc:
        return sop_transaction_error("Failed to create verified Boolean SOP", exc)


@skill_entry
def main(**kwargs) -> dict:
    return boolean_op(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
