"""Scan a network for all hlight nodes and report their state as a lighting summary."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _light_rig_common import (  # noqa: E402
    get_light_parms,
    get_node,
    is_light_node,
    is_rig_null,
)


def get_lighting_summary(parent_path: str = "/obj") -> dict:
    """Scan *parent_path* for all hlight nodes and report lighting state.

    Walks the network recursively and collects every ``hlight``/``hlight::2.0``
    node.  For each light, reports type, intensity, color, exposure, position,
    and rig membership (if parented under a null rig).  Also reports rig groups
    and totals.

    Args:
        parent_path: Network path to scan. Default ``/obj``.

    Returns:
        ToolResult with ``lights`` list, ``rigs`` list, and ``totals`` dict.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        lights = []
        rigs = []

        for child in parent.children():
            if is_rig_null(child):
                rig_lights = []
                for light_child in child.children():
                    if is_light_node(light_child):
                        parms = get_light_parms(light_child)
                        parms["rig_parent"] = child.path()
                        rig_lights.append(parms)
                        lights.append(parms)
                rigs.append(
                    {
                        "path": child.path(),
                        "name": child.name(),
                        "light_count": len(rig_lights),
                        "lights": [lt["path"] for lt in rig_lights],
                    }
                )
            elif is_light_node(child):
                parms = get_light_parms(child)
                parms["rig_parent"] = None
                lights.append(parms)

        # Collect standalone lights (not in a rig)
        standalone = [lt for lt in lights if lt.get("rig_parent") is None]
        rigged = [lt for lt in lights if lt.get("rig_parent") is not None]

        totals = {
            "total_lights": len(lights),
            "standalone_lights": len(standalone),
            "rigged_lights": len(rigged),
            "rig_groups": len(rigs),
        }

        # Aggregate light types
        type_counts: dict = {}
        for light in lights:
            light_type = light.get("type", "unknown")
            type_counts[light_type] = type_counts.get(light_type, 0) + 1
        totals["by_type"] = type_counts

        return skill_success(
            "Lighting summary: {} light(s), {} rig(s)".format(totals["total_lights"], totals["rig_groups"]),
            scanned_path=parent.path(),
            lights=lights,
            rigs=rigs,
            totals=totals,
            prompt="Use list_light_rigs to focus on rig groups or group_lights to organize standalone lights.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to get lighting summary")


@skill_entry
def main(**kwargs) -> dict:
    return get_lighting_summary(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
