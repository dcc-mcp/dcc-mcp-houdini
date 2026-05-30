"""Connect a shader output into a shader/VOP node input."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _lookdev_common import get_node, node_summary  # noqa: E402


def _resolve_index(node, input_index: Optional[int], input_name: Optional[str]) -> int:
    if input_index is not None:
        return int(input_index)
    if input_name is not None:
        try:
            names = list(node.inputNames())
            return names.index(input_name)
        except Exception:  # noqa: BLE001
            raise ValueError("No input named {!r}".format(input_name)) from None
    raise ValueError("Provide input_index or input_name")


def connect_shader(
    node_path: str,
    source_path: str,
    input_index: Optional[int] = None,
    input_name: Optional[str] = None,
    source_output: int = 0,
) -> dict:
    """Wire ``source_path`` (output) into ``node_path`` at an input slot."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        source = get_node(hou, source_path)
        index = _resolve_index(node, input_index, input_name)
        node.setInput(index, source, source_output)
        return skill_success(
            "Connected shader input",
            node=node_summary(node),
            input_index=index,
            source_path=source.path(),
            source_output=source_output,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to connect shader input")


@skill_entry
def main(**kwargs) -> dict:
    return connect_shader(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
