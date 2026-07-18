"""Connect one Houdini node's input to another node's output."""

from __future__ import annotations

from _graph_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def connect_input(
    node_path: str,
    input_index: int,
    source_path: str,
    source_output: int = 0,
) -> dict:
    """Wire ``source_path`` (output index) into ``node_path`` input ``input_index``."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        source = get_node(hou, source_path)
        node.setInput(input_index, source, source_output)
        return skill_success(
            "Connected input",
            node_path=node.path(),
            input_index=input_index,
            source_path=source.path(),
            source_output=source_output,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to connect input")


@skill_entry
def main(**kwargs) -> dict:
    return connect_input(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
