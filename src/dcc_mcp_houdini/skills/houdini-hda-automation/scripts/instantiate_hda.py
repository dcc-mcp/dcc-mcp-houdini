"""Instantiate an HDA, wire inputs, set parms, cook, and report results."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_auto_common import get_node, node_summary  # noqa: E402


def instantiate_hda(
    parent_path: str,
    node_type_name: str,
    hda_file: Optional[str] = None,
    node_name: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    inputs: Optional[List[str]] = None,
    cook: bool = True,
) -> dict:
    """Create an HDA instance under *parent_path* and configure it."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if hda_file:
            hou.hda.installFile(hda_file)
        parent = get_node(hou, parent_path)
        node = parent.createNode(node_type_name, node_name=node_name)
        warnings: List[str] = []

        if inputs:
            for index, source_path in enumerate(inputs):
                if not source_path:
                    continue
                source = hou.node(source_path)
                if source is None:
                    warnings.append("Input source not found: {}".format(source_path))
                    continue
                node.setInput(index, source)

        applied = {}
        if parameters:
            for name, value in parameters.items():
                if isinstance(value, (list, tuple)):
                    parm_tuple = node.parmTuple(name)
                    if parm_tuple is None:
                        warnings.append("No parm tuple {!r}".format(name))
                        continue
                    parm_tuple.set(tuple(value))
                    applied[name] = list(value)
                else:
                    parm = node.parm(name)
                    if parm is None:
                        warnings.append("No parm {!r}".format(name))
                        continue
                    parm.set(value)
                    applied[name] = value

        cook_error = None
        if cook:
            try:
                node.cook(force=True)
            except Exception as exc:  # noqa: BLE001
                cook_error = str(exc)
            if hasattr(node, "errors"):
                warnings.extend(list(node.errors()))

        generated = [child.path() for child in node.children()] if hasattr(node, "children") else []
        return skill_success(
            "Instantiated HDA",
            parent_path=parent.path(),
            node=node_summary(node),
            applied=applied,
            generated_nodes=generated,
            cook_error=cook_error,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to instantiate HDA")


@skill_entry
def main(**kwargs) -> dict:
    return instantiate_hda(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
