"""Disconnect a Houdini node's input."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _graph_common import get_node  # noqa: E402


def disconnect_input(node_path: str, input_index: int) -> dict:
    """Clear the connection feeding ``input_index`` on ``node_path``."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        node.setInput(input_index, None)
        return skill_success(
            "Disconnected input",
            node_path=node.path(),
            input_index=input_index,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to disconnect input")


@skill_entry
def main(**kwargs) -> dict:
    return disconnect_input(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
