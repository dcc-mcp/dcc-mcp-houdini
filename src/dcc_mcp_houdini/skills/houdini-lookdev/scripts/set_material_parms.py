"""Set material/shader parameter values with type-aware coercion."""

from __future__ import annotations

from typing import Any, Dict

from _lookdev_common import get_node, node_summary, set_parameters  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_material_parms(material_path: str, parameters: Dict[str, Any]) -> dict:
    """Set the given parameters on the material at *material_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, material_path)
        applied, errors = set_parameters(node, parameters)
        if not applied and errors:
            return skill_error(
                "No parameters set",
                "All parameters failed validation",
                material=node_summary(node),
                errors=errors,
            )
        return skill_success(
            "Set material parameters",
            material=node_summary(node),
            applied=applied,
            errors=errors,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set material parameters")


@skill_entry
def main(**kwargs) -> dict:
    return set_material_parms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
