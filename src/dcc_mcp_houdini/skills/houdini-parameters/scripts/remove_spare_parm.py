"""Remove a spare parameter from a Houdini node."""

from __future__ import annotations

from _parm_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def remove_spare_parm(node_path: str, name: str) -> dict:
    """Remove the spare parameter tuple named *name*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parm_tuple = node.parmTuple(name)
        if parm_tuple is None:
            return skill_error(
                "Parameter not found",
                "No parameter tuple named {!r}".format(name),
                node_path=node.path(),
            )
        node.removeSpareParmTuple(parm_tuple)
        return skill_success(
            "Removed spare parameter",
            node_path=node.path(),
            name=name,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to remove spare parameter")


@skill_entry
def main(**kwargs) -> dict:
    return remove_spare_parm(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
