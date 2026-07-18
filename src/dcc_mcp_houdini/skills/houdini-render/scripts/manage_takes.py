"""Manage Houdini takes — create, switch, delete, and list takes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


def manage_takes(
    action: str = "list",
    take_name: Optional[str] = None,
    node_path: Optional[str] = None,
    parm_name: Optional[str] = None,
    value: Any = None,
) -> dict:
    """Manage takes and their parameter-tuple overrides."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        takes = hou.takes
        current = takes.currentTake()

        if action == "list":
            take_list = []
            for t in takes.takes():
                take_list.append(
                    {
                        "name": t.name(),
                        "is_current": t == current,
                        "num_nodes": len(list(t.nodes())) if hasattr(t, "nodes") else -1,
                    }
                )
            return skill_success(
                "Listed takes",
                current_take=current.name(),
                takes=take_list,
            )

        if action == "create":
            if not take_name:
                return skill_error("Missing take_name", "take_name is required for action=create")
            existing = takes.findTake(take_name)
            if existing:
                return skill_error(
                    "Take already exists",
                    "A take named '{}' already exists".format(take_name),
                    take_name=take_name,
                )
            takes.rootTake().addChildTake(take_name)
            return skill_success(
                "Created take",
                take_name=take_name,
                current_take=current.name(),
            )

        if action in ("add_override", "remove_override"):
            if action == "remove_override" and value is not None:
                return skill_error(
                    "Invalid value",
                    "value is supported only for action=add_override",
                    action=action,
                )
            if not take_name:
                return skill_error("Missing take_name", "take_name is required for action={}".format(action))
            target = takes.findTake(take_name)
            if not target:
                return skill_error(
                    "Take not found",
                    "Take '{}' does not exist".format(take_name),
                    take_name=take_name,
                )
            if target.parent() is None:
                return skill_error("Invalid take", "Parameter overrides require a child take")
            if not node_path or not parm_name:
                return skill_error(
                    "Missing parameter",
                    "node_path and parm_name are required for action={}".format(action),
                )
            node = hou.node(node_path)
            if node is None:
                return skill_error("Node not found", "Houdini node not found: {}".format(node_path))
            parm_tuple = node.parmTuple(parm_name)
            if parm_tuple is None:
                parm = node.parm(parm_name)
                tuple_method = getattr(parm, "tuple", None)
                parm_tuple = tuple_method() if callable(tuple_method) else None
            if parm_tuple is None:
                return skill_error(
                    "Parameter not found",
                    "Parameter tuple '{}' was not found on '{}'".format(parm_name, node_path),
                )

            changed = False
            value_applied = False
            takes.setCurrentTake(target)
            try:
                included = target.hasParmTuple(parm_tuple)
                if action == "add_override" and not included:
                    target.addParmTuple(parm_tuple)
                    changed = True
                elif action == "remove_override" and included:
                    target.removeParmTuple(parm_tuple)
                    changed = True
                if action == "add_override" and value is not None:
                    values = tuple(value) if isinstance(value, (list, tuple)) else (value,)
                    try:
                        parm_tuple.set(values)
                    except Exception:
                        if changed:
                            target.removeParmTuple(parm_tuple)
                        raise
                    value_applied = True
                return skill_success(
                    "Updated take parameter override",
                    action=action,
                    take_name=take_name,
                    node_path=node_path,
                    parm_name=parm_name,
                    changed=changed,
                    value_applied=value_applied,
                )
            finally:
                if takes.currentTake() != current:
                    takes.setCurrentTake(current)

        if action == "switch":
            if not take_name:
                return skill_error("Missing take_name", "take_name is required for action=switch")
            target = takes.findTake(take_name)
            if not target:
                return skill_error(
                    "Take not found",
                    "Take '{}' does not exist".format(take_name),
                    take_name=take_name,
                )
            takes.setCurrentTake(target)
            return skill_success(
                "Switched take",
                take_name=take_name,
                previous_take=current.name(),
            )

        if action == "delete":
            if not take_name:
                return skill_error("Missing take_name", "take_name is required for action=delete")
            target = takes.findTake(take_name)
            if not target:
                return skill_error(
                    "Take not found",
                    "Take '{}' does not exist".format(take_name),
                    take_name=take_name,
                )
            if target == current:
                return skill_error(
                    "Cannot delete current take",
                    "Switch to another take before deleting '{}'".format(take_name),
                )
            target.destroy()
            return skill_success(
                "Deleted take",
                take_name=take_name,
                current_take=current.name(),
            )

        return skill_error(
            "Unknown action",
            "Action must be one of: list, create, switch, delete, add_override, remove_override",
            action=action,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to manage takes")


@skill_entry
def main(**kwargs) -> dict:
    return manage_takes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
