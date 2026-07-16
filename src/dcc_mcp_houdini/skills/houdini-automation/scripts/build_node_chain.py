"""Build a small Houdini node chain from structured specs."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _atomic_node_chain import (
    AtomicNodeChainExecutor,
    NodeChainExecutionError,
    NodeChainValidationError,
    NodeChainValidator,
)
from _automation_common import hou_import_error, node_summary, set_parm_value


def build_node_chain(
    parent_path: str,
    nodes: List[Dict[str, Any]],
    connections: Optional[List[Dict[str, Any]]] = None,
    layout: bool = True,
    cook_last: bool = True,
    dry_run: bool = False,
) -> dict:
    """Validate and atomically build a node recipe with readback evidence."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    transaction_id = uuid.uuid4().hex
    undo_label = "DCC MCP: build_node_chain {}".format(transaction_id)
    try:
        plan = NodeChainValidator(hou).validate(
            parent_path,
            nodes,
            connections,
            layout=layout,
            cook_last=cook_last,
        )
    except NodeChainValidationError as exc:
        return skill_error(
            "Invalid Houdini node chain",
            str(exc),
            transaction_id=transaction_id,
            undo_label=undo_label,
            dry_run=bool(dry_run),
            affected_paths=[],
            validated={"valid": False, "errors": exc.errors},
            readback={"performed": False},
            rollback={"attempted": False, "complete": True, "errors": []},
        )
    except Exception as exc:
        return skill_exception(
            exc,
            message="Failed to validate Houdini node chain",
            transaction_id=transaction_id,
            undo_label=undo_label,
            dry_run=bool(dry_run),
        )

    validated = plan.validated_summary()
    affected_paths = plan.predicted_affected_paths()
    if dry_run:
        return skill_success(
            "Validated Houdini node chain",
            transaction_id=transaction_id,
            undo_label=undo_label,
            dry_run=True,
            affected_paths=affected_paths,
            validated=validated,
            readback={"performed": False},
            rollback={"attempted": False, "complete": True, "errors": []},
        )

    try:
        execution = AtomicNodeChainExecutor(hou, set_parm_value, node_summary).execute(
            plan,
            undo_label,
        )
    except NodeChainExecutionError as exc:
        return skill_error(
            "Failed to build Houdini node chain",
            "{}: {}".format(type(exc.cause).__name__, exc.cause),
            transaction_id=transaction_id,
            undo_label=undo_label,
            dry_run=False,
            affected_paths=exc.affected_paths,
            validated=validated,
            readback={"performed": False},
            rollback=exc.rollback,
        )
    except Exception as exc:
        return skill_exception(
            exc,
            message="Failed to build Houdini node chain",
            transaction_id=transaction_id,
            undo_label=undo_label,
            dry_run=False,
            affected_paths=affected_paths,
            validated=validated,
        )

    return skill_success(
        "Built Houdini node chain",
        transaction_id=transaction_id,
        undo_label=undo_label,
        dry_run=False,
        parent_path=plan.parent.path(),
        affected_paths=list(execution.affected_paths),
        validated=validated,
        readback=execution.readback,
        rollback={"attempted": False, "complete": True, "errors": []},
        nodes=[node_summary(node) for node in execution.nodes],
        cooked_node=(node_summary(execution.cooked_node) if execution.cooked_node is not None else None),
    )


@skill_entry
def main(**kwargs) -> dict:
    return build_node_chain(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
