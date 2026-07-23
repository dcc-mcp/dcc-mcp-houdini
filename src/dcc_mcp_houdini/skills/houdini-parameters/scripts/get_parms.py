"""Read one or more parameter values from a Houdini node."""

from __future__ import annotations

from typing import List, Optional

from _parm_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini.api import safe_parm_eval


def get_parms(node_path: str, names: Optional[List[str]] = None) -> dict:
    """Return values for the requested parm names (all parms when omitted)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        values = {}
        missing = []
        if names:
            for name in names:
                parm_tuple = node.parmTuple(name)
                parm = node.parm(name)
                if parm_tuple is not None and parm is None:
                    values[name] = list(parm_tuple.eval())
                elif parm is not None:
                    values[name] = safe_parm_eval(parm)
                else:
                    missing.append(name)
        else:
            for parm in node.parms():
                values[parm.name()] = safe_parm_eval(parm)
        return skill_success(
            "Read parameters",
            node_path=node.path(),
            values=values,
            missing=missing,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read parameters")


@skill_entry
def main(**kwargs) -> dict:
    return get_parms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
