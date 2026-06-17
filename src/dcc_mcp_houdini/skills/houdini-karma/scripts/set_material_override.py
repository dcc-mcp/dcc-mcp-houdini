"""Set a global material override on a Karma render node for lookdev/testing."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _karma_common import get_node, node_summary, set_first_parm, set_parm_if_exists  # noqa: E402

# Common override materials with their shader paths
OVERRIDE_PRESETS = {
    "clay": {"shader": "karma_materialbuilder", "color": [0.7, 0.6, 0.5], "roughness": 0.5},
    "gray": {"shader": "karma_materialbuilder", "color": [0.5, 0.5, 0.5], "roughness": 0.4},
    "white": {"shader": "karma_materialbuilder", "color": [0.9, 0.9, 0.9], "roughness": 0.3},
    "chrome": {"shader": "karma_materialbuilder", "color": [0.95, 0.95, 0.95], "roughness": 0.05, "metallic": 1.0},
    "checker": {"shader": "karma_materialbuilder", "color": [0.8, 0.3, 0.3], "roughness": 0.4},
    "normals": {"shader": "karma_materialbuilder", "type": "normal_debug"},
    "uv": {"shader": "karma_materialbuilder", "type": "uv_debug"},
}


def set_material_override(
    node_path: str,
    material_path: Optional[str] = None,
    preset: Optional[str] = None,
    color: Optional[list] = None,
    roughness: Optional[float] = None,
    metallic: Optional[float] = None,
    clear: bool = False,
) -> dict:
    """Set or clear a global material override on a Karma render node."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        applied: dict = {}

        if clear:
            # Clear the override — try multiple parm names
            cleared_parms = []
            for parm_name in ("material_override", "matoverride", "globalmaterial", "override_material"):
                if set_parm_if_exists(node, parm_name, ""):
                    cleared_parms.append(parm_name)
            if cleared_parms:
                applied["cleared"] = cleared_parms
                return skill_success(
                    "Cleared material override",
                    node=node_summary(node),
                    applied=applied,
                )
            else:
                return skill_success(
                    "No material override to clear",
                    node=node_summary(node),
                    hint="Node does not have a material override parameter",
                )

        # Resolve material from preset or explicit path
        mat_path = material_path
        if not mat_path and preset:
            preset_info = OVERRIDE_PRESETS.get(preset.lower())
            if not preset_info:
                return skill_error(
                    "Unknown preset",
                    "Preset '{}' not found. Available: {}".format(preset, ", ".join(OVERRIDE_PRESETS.keys())),
                )
            mat_path = "/mat/{}".format(preset)
            applied["preset"] = preset
            applied["preset_params"] = preset_info

        if not mat_path:
            return skill_error(
                "Missing material",
                "Provide material_path or preset name",
            )

        # Set the override parameter
        used = set_first_parm(
            node,
            ("material_override", "matoverride", "globalmaterial", "override_material"),
            mat_path,
        )
        if used:
            applied["material_path"] = mat_path
        else:
            applied["material_path"] = "{} (unsupported — node may not support material override)".format(mat_path)

        # Optionally set override properties
        if color and len(color) >= 3:
            set_first_parm(node, ("override_color", "mat_override_color"), color)
            applied["color"] = color
        if roughness is not None:
            set_first_parm(node, ("override_roughness", "mat_override_roughness"), float(roughness))
            applied["roughness"] = float(roughness)
        if metallic is not None:
            set_first_parm(node, ("override_metallic", "mat_override_metallic"), float(metallic))
            applied["metallic"] = float(metallic)

        return skill_success(
            "Set material override",
            node=node_summary(node),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set material override")


@skill_entry
def main(**kwargs) -> dict:
    return set_material_override(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
