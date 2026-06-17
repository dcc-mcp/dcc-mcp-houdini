"""Configure Karma Light Mixer panel — adjust individual light contributions."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _karma_common import get_node, node_summary, set_first_parm  # noqa: E402


def configure_light_mixer(
    node_path: str,
    lights: Optional[List[dict]] = None,
    enable: bool = True,
    auto_create: bool = False,
) -> dict:
    """Enable/configure the Karma Light Mixer and adjust per-light contributions.

    *lights* is a list of dicts with keys: name, intensity, exposure, color.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        applied: dict = {}

        # Enable light mixer
        mixer_enabled = set_first_parm(
            node,
            ("enable_lightmixer", "lightmixer_enable", "enable_light_mixer"),
            int(enable),
        )
        applied["light_mixer_enabled"] = enable if mixer_enabled else "unsupported"

        if auto_create:
            created = set_first_parm(
                node,
                ("create_lightmixer", "auto_create_lightmixer"),
                1,
            )
            applied["auto_create"] = bool(created)

        # Configure per-light contributions
        light_results: list = []
        if lights:
            for light in lights:
                light_name = light.get("name")
                if not light_name:
                    continue
                result: dict = {"name": light_name}
                prefix = light_name.replace(" ", "_").replace("/", "_")
                if "intensity" in light:
                    set_first_parm(
                        node,
                        ("lm_{}_intensity".format(prefix), "lightmixer_{}_intensity".format(prefix)),
                        float(light["intensity"]),
                    )
                    result["intensity"] = float(light["intensity"])
                if "exposure" in light:
                    set_first_parm(
                        node,
                        ("lm_{}_exposure".format(prefix), "lightmixer_{}_exposure".format(prefix)),
                        float(light["exposure"]),
                    )
                    result["exposure"] = float(light["exposure"])
                if "color" in light and len(light["color"]) >= 3:
                    set_first_parm(
                        node,
                        ("lm_{}_color".format(prefix), "lightmixer_{}_color".format(prefix)),
                        [float(c) for c in light["color"][:3]],
                    )
                    result["color"] = light["color"]
                light_results.append(result)
            applied["lights"] = light_results

        return skill_success(
            "Configured Light Mixer",
            node=node_summary(node),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure light mixer")


@skill_entry
def main(**kwargs) -> dict:
    return configure_light_mixer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
