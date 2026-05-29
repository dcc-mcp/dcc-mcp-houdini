"""Inspect a Houdini node's inputs, outputs, and dependents."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _graph_common import get_node, paths_or_none  # noqa: E402


def get_connections(node_path: str, include_dependents: bool = True) -> dict:
    """Return inputs, outputs, and (optionally) parameter/reference dependents."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        inputs = paths_or_none(node.inputs())
        outputs = paths_or_none(node.outputs())
        context = {
            "node_path": node.path(),
            "inputs": inputs,
            "outputs": outputs,
        }
        if include_dependents and hasattr(node, "dependents"):
            try:
                context["dependents"] = paths_or_none(node.dependents())
            except Exception:  # noqa: BLE001
                context["dependents"] = []
        return skill_success("Read connections", **context)
    except Exception as exc:
        return skill_exception(exc, message="Failed to read connections")


@skill_entry
def main(**kwargs) -> dict:
    return get_connections(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
