"""Group existing hlight nodes under a new null rig node for collective control."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _light_rig_common import (  # noqa: E402
    get_node,
    is_light_node,
)


def group_lights(
    rig_name: str,
    light_paths: List[str],
    parent_path: str = "/obj",
) -> dict:
    """Group one or more existing hlight nodes under a new null rig node.

    Creates a null node at *parent_path* and re-parents the specified lights
    underneath it.  The result is a rig group that tools like
    ``set_light_rig_intensity`` and ``list_light_rigs`` can operate on.

    Args:
        rig_name: Name for the new rig null group node.
        light_paths: Paths of ``hlight`` nodes to group under the rig.
        parent_path: Parent network where the rig null is created.
            Default ``/obj``.

    Returns:
        ToolResult with ``rig_path``, ``member_count``, and ``members``
        list of grouped light paths.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if not light_paths:
        return skill_error("No light paths provided", "light_paths must contain at least one path")

    try:
        parent = get_node(hou, parent_path)

        # Create the rig null
        rig = parent.createNode("null", node_name=rig_name)

        grouped = []
        skipped = []

        for light_path in light_paths:
            try:
                light = get_node(hou, light_path)
                if not is_light_node(light):
                    skipped.append({
                        "path": light_path,
                        "reason": "Not an hlight node (type: {})".format(
                            light.type().name()
                        ),
                    })
                    continue
                # Set parent to the rig null
                light.setParent(rig)
                grouped.append({
                    "path": light.path(),
                    "name": light.name(),
                })
            except Exception as exc:
                skipped.append({
                    "path": light_path,
                    "reason": str(exc),
                })

        warnings = None
        if skipped:
            warnings = {
                "skipped_count": len(skipped),
                "skipped": skipped,
            }

        return skill_success(
            "Grouped {} light(s) under rig '{}'".format(len(grouped), rig.name()),
            rig_path=rig.path(),
            rig_name=rig.name(),
            member_count=len(grouped),
            members=grouped,
            warnings=warnings,
            prompt="Use set_light_rig_intensity to adjust all lights in the rig, or list_light_rigs to review.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to group lights under rig '{}'".format(rig_name))


@skill_entry
def main(**kwargs) -> dict:
    return group_lights(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
