"""Inspect parameter templates on a Houdini node."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _parm_common import get_node, template_info  # noqa: E402


def get_parm_templates(node_path: str, parm_name: Optional[str] = None) -> dict:
    """Return parm-template metadata for one parm or every top-level template."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        if parm_name:
            parm = node.parm(parm_name) or node.parmTuple(parm_name)
            if parm is None:
                return skill_error(
                    "Parameter not found",
                    "No parameter named {!r}".format(parm_name),
                    node_path=node.path(),
                )
            return skill_success(
                "Read parameter template",
                node_path=node.path(),
                template=template_info(parm.parmTemplate()),
            )
        group = node.parmTemplateGroup()
        templates = [template_info(t) for t in group.entries()]
        return skill_success(
            "Read parameter templates",
            node_path=node.path(),
            templates=templates,
            count=len(templates),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read parameter templates")


@skill_entry
def main(**kwargs) -> dict:
    return get_parm_templates(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
