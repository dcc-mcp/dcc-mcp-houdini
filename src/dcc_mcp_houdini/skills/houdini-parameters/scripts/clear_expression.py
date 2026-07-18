"""Clear a channel expression on a Houdini parameter, keeping its value."""

from __future__ import annotations

from _parm_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def clear_expression(node_path: str, parm_name: str) -> dict:
    """Remove any expression/keyframes on the parm, freezing the current value."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parm = node.parm(parm_name)
        if parm is None:
            return skill_error(
                "Parameter not found",
                "No parameter named {!r}".format(parm_name),
                node_path=node.path(),
            )
        frozen = parm.eval()
        parm.deleteAllKeyframes()
        parm.set(frozen)
        return skill_success(
            "Cleared expression",
            node_path=node.path(),
            parm=parm_name,
            value=frozen,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to clear expression")


@skill_entry
def main(**kwargs) -> dict:
    return clear_expression(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
