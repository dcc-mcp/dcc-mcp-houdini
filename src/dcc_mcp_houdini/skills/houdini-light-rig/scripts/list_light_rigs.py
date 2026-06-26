"""List all light rig groups (null nodes containing hlight children) in a network."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _light_rig_common import (  # noqa: E402
    get_node,
    get_rig_members,
    is_rig_null,
)


def list_light_rigs(parent_path: str = "/obj") -> dict:
    """List light rig groups under *parent_path*.

    A light rig is a null node whose children include at least one
    ``hlight``/``hlight::2.0`` node.  Reports rig name, path, light count,
    and member light paths with brief parameter summaries.

    Args:
        parent_path: Network path to search. Default ``/obj``.

    Returns:
        ToolResult with ``rigs`` list and ``count``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        rigs = []

        for child in parent.children():
            if not is_rig_null(child):
                continue

            members = get_rig_members(child)
            member_info = []
            for light in members:
                # Read key parms via _light_rig_common
                from _light_rig_common import eval_parm  # noqa: PLC0415

                member_info.append(
                    {
                        "path": light.path(),
                        "name": light.name(),
                        "intensity": eval_parm(light, "light_intensity"),
                        "enabled": eval_parm(light, "light_enable"),
                    }
                )

            rigs.append(
                {
                    "path": child.path(),
                    "name": child.name(),
                    "light_count": len(members),
                    "lights": member_info,
                }
            )

        return skill_success(
            "Listed {} light rig(s)".format(len(rigs)),
            scanned_path=parent.path(),
            count=len(rigs),
            rigs=rigs,
            prompt="Use set_light_rig_intensity to adjust a rig or get_lighting_summary for full lighting details.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list light rigs")


@skill_entry
def main(**kwargs) -> dict:
    return list_light_rigs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
