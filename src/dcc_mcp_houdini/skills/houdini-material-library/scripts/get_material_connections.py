"""Query a material/shader node's input and output connections (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _library_common import find_image_filepath, get_node, hou_import_error, node_summary  # noqa: E402


def _connection_info(source_node: Any) -> dict:
    """Return a JSON-safe summary of a connected source node."""
    info = node_summary(source_node)
    # Check if it's an image node.
    filepath = find_image_filepath(source_node)
    if filepath:
        info["image_file"] = filepath
    return info


def _traverse_upstream(node: Any, depth: int, visited: set) -> List[dict]:
    """Recursively collect upstream connections up to *depth* levels."""
    if depth <= 0 or node.path() in visited:
        return []
    visited.add(node.path())
    result: List[dict] = []
    for i, source in enumerate(node.inputs()):
        if source is None:
            continue
        info = _connection_info(source)
        info["input_index"] = i
        info["upstream"] = _traverse_upstream(source, depth - 1, visited)
        result.append(info)
    return result


def get_material_connections(material_path: str, depth: int = 1) -> dict:
    """Query a material/shader node's connections.

    Args:
        material_path: Path to the material/shader node.
        depth: Upstream traversal depth (1 = direct inputs only).

    Returns:
        ToolResult dict with inputs and outputs.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        node = get_node(hou, material_path)

        # Input connections.
        try:
            input_names = list(node.inputNames())
        except Exception:  # noqa: BLE001
            input_names = []

        inputs = []
        visited: set = set()
        visited.add(node.path())
        for index, source in enumerate(node.inputs()):
            if source is None:
                continue
            name = input_names[index] if index < len(input_names) else None
            info = _connection_info(source)
            info["input_index"] = index
            info["input_name"] = name
            info["upstream"] = _traverse_upstream(source, depth - 1, visited)
            inputs.append(info)

        # Output connections.
        outputs = []
        try:
            for out_node in node.outputs():
                outputs.append(node_summary(out_node))
        except Exception:  # noqa: BLE001
            pass

        # Material assignments on renderable objects.
        assignments: List[dict] = []
        material_path_normalized = node.path()
        try:
            obj_root = hou.node("/obj")
            if obj_root is not None:
                # Walk /obj for any node referencing this material.
                for child in obj_root.allSubChildren():
                    shop_parm = child.parm("shop_materialpath")
                    if shop_parm is None:
                        shop_parm = child.parm("shop_materialpath1")
                    if shop_parm is None:
                        continue
                    try:
                        shop_val = shop_parm.eval()
                    except Exception:  # noqa: BLE001
                        continue
                    if shop_val == material_path_normalized:
                        assignments.append({"object_path": child.path(), "object_name": child.name()})
        except Exception:  # noqa: BLE001
            pass

        return skill_success(
            "Read material connections",
            node=node_summary(node),
            input_count=len(inputs),
            output_count=len(outputs),
            assignment_count=len(assignments),
            inputs=inputs,
            outputs=outputs,
            assignments=assignments if assignments else None,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to get material connections")


@skill_entry
def main(**kwargs) -> dict:
    return get_material_connections(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
