"""Delete a constraint node from the scene."""

from __future__ import annotations

from _constraint_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def delete_constraint(node_path: str) -> dict:
    """Delete the constraint node at *node_path*.

    Clears expression-driven channels on any driven objects (blend constraints)
    before destroying the constraint node itself.  This is a **destructive**
    operation — the constraint is permanently removed.

    Args:
        node_path: Path to the constraint node to delete.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        node_info = {
            "path": node.path(),
            "name": node.name(),
            "type": node.type().name(),
        }

        # For blend constraints, clear expressions on driven objects first.
        if node.type().name() == "blend":
            # Look for parms referencing this blend node via ch() expression.
            parent = node.parent()
            for child in parent.children():
                if child.path() == node.path():
                    continue
                for parm in child.parms():
                    try:
                        raw = parm.rawValue()
                        if isinstance(raw, str) and node.name() in raw:
                            parm.revertToDefaults()
                    except Exception:  # noqa: BLE001
                        pass

        node.destroy()

        return skill_success(
            "Deleted constraint",
            deleted_node=node_info,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to delete constraint")


@skill_entry
def main(**kwargs) -> dict:
    return delete_constraint(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
