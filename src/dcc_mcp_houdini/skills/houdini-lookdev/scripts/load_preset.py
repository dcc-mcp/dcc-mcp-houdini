"""Apply a saved material preset onto a material/shader node."""

from __future__ import annotations

import json

from _lookdev_common import get_node, node_summary, preset_dir, set_parameters  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def load_preset(preset_name: str, material_path: str) -> dict:
    """Apply the parameters from *preset_name* onto *material_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    target = preset_dir() / "{}.json".format(preset_name)
    if not target.is_file():
        # Allow passing the sanitized stem directly.
        candidates = list(preset_dir().glob("{}.json".format(preset_name)))
        if not candidates:
            return skill_error(
                "Preset not found",
                "No preset named {!r}".format(preset_name),
                preset_dir=str(preset_dir()),
            )
        target = candidates[0]

    try:
        with open(target, encoding="utf-8") as handle:
            data = json.load(handle)
        node = get_node(hou, material_path)
        material_type = data.get("material_type")
        warnings = []
        if material_type and node.type().name() != material_type:
            warnings.append("Preset is for {!r}; target is {!r}".format(material_type, node.type().name()))
        applied, errors = set_parameters(node, data.get("parameters", {}))
        return skill_success(
            "Loaded material preset",
            preset_name=preset_name,
            material=node_summary(node),
            applied_count=len(applied),
            errors=errors,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to load material preset")


@skill_entry
def main(**kwargs) -> dict:
    return load_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
