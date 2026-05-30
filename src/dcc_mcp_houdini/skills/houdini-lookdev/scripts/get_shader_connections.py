"""Inspect a shader/VOP node's input and output connections (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _lookdev_common import get_node, node_summary  # noqa: E402


def get_shader_connections(node_path: str) -> dict:
    """Return input/output connections for the shader node at *node_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        try:
            input_names = list(node.inputNames())
        except Exception:  # noqa: BLE001
            input_names = []
        inputs = []
        for index, source in enumerate(node.inputs()):
            name = input_names[index] if index < len(input_names) else None
            inputs.append(
                {
                    "index": index,
                    "name": name,
                    "source": source.path() if source is not None else None,
                }
            )
        outputs = [n.path() for n in node.outputs()] if hasattr(node, "outputs") else []
        return skill_success(
            "Read shader connections",
            node=node_summary(node),
            inputs=inputs,
            outputs=outputs,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read shader connections")


@skill_entry
def main(**kwargs) -> dict:
    return get_shader_connections(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
