"""Scale or set intensity of all lights parented under a rig null group."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _light_rig_common import (  # noqa: E402
    eval_parm,
    get_node,
    get_rig_members,
    set_parm_if_exists,
)

logger = logging.getLogger(__name__)


def set_light_rig_intensity(
    rig_group: str,
    intensity: float,
    multiply: bool = False,
) -> dict:
    """Scale or set the intensity of every light under a rig null group.

    Args:
        rig_group: Path to the rig null group node.
        intensity: New intensity value (absolute) or multiplier when
            ``multiply=True``.
        multiply: If True, multiply each light's current intensity by
            *intensity* instead of setting an absolute value.
            Default False.

    Returns:
        ToolResult with ``rig_group``, ``updated_lights`` list, and
        ``light_count``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        rig = get_node(hou, rig_group)
        members = get_rig_members(rig)

        if not members:
            return skill_error(
                "No lights found under rig '{}'".format(rig_group),
                "The rig group contains no hlight children.",
                rig_group=rig_group,
            )

        updated = []
        for light in members:
            try:
                if multiply:
                    current = eval_parm(light, "light_intensity")
                    if current is None:
                        continue
                    new_val = float(current) * float(intensity)
                else:
                    new_val = float(intensity)
                if set_parm_if_exists(light, "light_intensity", new_val):
                    updated.append(
                        {
                            "path": light.path(),
                            "name": light.name(),
                            "intensity": new_val,
                        }
                    )
            except Exception as exc:
                logger.warning("Could not set intensity on %s: %s", light.path(), exc)

        mode = "multiplied" if multiply else "set"
        return skill_success(
            "{} intensity on {} light(s) in rig '{}'".format(mode.capitalize(), len(updated), rig.name()),
            rig_group=rig_group,
            updated_lights=updated,
            light_count=len(updated),
            mode=mode,
            prompt="Use list_light_rigs or get_lighting_summary to review updated intensities.",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set intensity for rig '{}'".format(rig_group))


@skill_entry
def main(**kwargs) -> dict:
    return set_light_rig_intensity(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
