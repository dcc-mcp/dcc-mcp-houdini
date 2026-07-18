"""Connect Houdini nodes."""

from __future__ import annotations

from _node_common import get_node, hou_import_error
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def connect_nodes(
    input_node_path: str,
    output_node_path: str,
    input_index: int = 0,
    output_index: int = 0,
) -> dict:
    """Connect output_node_path into input_node_path."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        input_node = get_node(hou, input_node_path)
        output_node = get_node(hou, output_node_path)
        input_node.setInput(input_index, output_node, output_index)
        return skill_success(
            "Connected Houdini nodes",
            input_node=input_node.path(),
            output_node=output_node.path(),
            input_index=input_index,
            output_index=output_index,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to connect Houdini nodes")


@skill_entry
def main(**kwargs) -> dict:
    return connect_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
