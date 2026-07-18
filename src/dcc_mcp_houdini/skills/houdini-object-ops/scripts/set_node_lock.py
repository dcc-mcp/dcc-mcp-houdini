"""Lock or unlock a Houdini node's cooked contents."""

from __future__ import annotations

from _object_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_node_lock(node_path: str, locked: bool) -> dict:
    """Hard-lock (freeze) or unlock the node at *node_path*.

    Uses ``setHardLocked`` when the node supports it (SOP-style nodes); returns
    a structured error otherwise so the caller can choose a different node.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        setter = getattr(node, "setHardLocked", None)
        if setter is None:
            return skill_error(
                "Lock unsupported",
                "Node type does not support hard locking: {}".format(node_path),
                possible_solutions=["Target a SOP node that supports setHardLocked"],
            )
        setter(bool(locked))
        return skill_success(
            "Updated node lock",
            node_path=node.path(),
            locked=bool(locked),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set node lock")


@skill_entry
def main(**kwargs) -> dict:
    return set_node_lock(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
