"""Disconnect a shader/VOP node input."""

from __future__ import annotations

from _lookdev_common import get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def disconnect_shader(node_path: str, input_index: int) -> dict:
    """Clear the input at *input_index* on the shader node at *node_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        previous = None
        try:
            inputs = node.inputs()
            if int(input_index) < len(inputs) and inputs[int(input_index)] is not None:
                previous = inputs[int(input_index)].path()
        except Exception:  # noqa: BLE001
            previous = None
        node.setInput(int(input_index), None)
        return skill_success(
            "Disconnected shader input",
            node=node_summary(node),
            input_index=int(input_index),
            previous_source=previous,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to disconnect shader input")


@skill_entry
def main(**kwargs) -> dict:
    return disconnect_shader(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
