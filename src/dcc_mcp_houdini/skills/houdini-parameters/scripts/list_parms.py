"""List the parameters on a Houdini node."""

from __future__ import annotations

from typing import Optional

from _parm_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini.api import safe_parm_eval


def list_parms(node_path: str, name_filter: Optional[str] = None) -> dict:
    """List parameters with name, label, and current value.

    ``name_filter`` is an optional case-insensitive substring on the parm name.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parms = []
        for parm in node.parms():
            name = parm.name()
            if name_filter and name_filter.lower() not in name.lower():
                continue
            try:
                value = safe_parm_eval(parm)
            except Exception:  # noqa: BLE001
                value = None
            entry = {"name": name, "value": value}
            label = getattr(parm, "label", None)
            if callable(label):
                try:
                    entry["label"] = parm.label()
                except Exception:  # noqa: BLE001
                    pass
            parms.append(entry)
        return skill_success(
            "Listed parameters",
            node_path=node.path(),
            parms=parms,
            count=len(parms),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list parameters")


@skill_entry
def main(**kwargs) -> dict:
    return list_parms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
