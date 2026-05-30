"""Validate an HDA node: report errors, warnings, and missing references."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_auto_common import get_node, node_summary  # noqa: E402


def validate_hda(node_path: str, cook: bool = True) -> dict:
    """Cook the node (optional) and collect errors/warnings as a verdict."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        cook_error = None
        if cook:
            try:
                node.cook(force=True)
            except Exception as exc:  # noqa: BLE001
                cook_error = str(exc)

        errors = list(node.errors()) if hasattr(node, "errors") else []
        warnings = list(node.warnings()) if hasattr(node, "warnings") else []
        valid = not errors and cook_error is None
        return skill_success(
            "Validated HDA node" if valid else "HDA node reported issues",
            node=node_summary(node),
            valid=valid,
            errors=errors,
            warnings=warnings,
            cook_error=cook_error,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate HDA node")


@skill_entry
def main(**kwargs) -> dict:
    return validate_hda(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
