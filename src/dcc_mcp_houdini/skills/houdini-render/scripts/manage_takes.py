"""Manage Houdini takes — create, switch, delete, and list takes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


def manage_takes(
    action: str = "list",
    take_name: Optional[str] = None,
) -> dict:
    """Create, switch, delete, or list takes in the current Houdini session."""
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
                take_list.append({
                    "name": t.name(),
                    "is_current": t == current,
                    "num_nodes": len(list(t.nodes())) if hasattr(t, "nodes") else -1,
                })
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
            takes.createTake(take_name)
            return skill_success(
                "Created take",
                take_name=take_name,
                current_take=current.name(),
            )

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
            "Action must be one of: list, create, switch, delete",
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
