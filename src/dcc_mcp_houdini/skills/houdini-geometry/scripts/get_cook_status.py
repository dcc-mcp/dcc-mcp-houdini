"""Cook a SOP node and report errors/warnings."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _geo_common import get_node  # noqa: E402


def get_cook_status(node_path: str, force: bool = False) -> dict:
    """Cook *node_path* and return any cook errors and warnings."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        cook_error = None
        try:
            node.cook(force=force)
        except Exception as exc:  # noqa: BLE001 - surface cook failure as data
            cook_error = str(exc)
        errors = list(node.errors()) if hasattr(node, "errors") else []
        warnings = list(node.warnings()) if hasattr(node, "warnings") else []
        return skill_success(
            "Cooked node",
            node_path=node.path(),
            cooked=cook_error is None,
            cook_error=cook_error,
            errors=errors,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to cook node")


@skill_entry
def main(**kwargs) -> dict:
    return get_cook_status(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
