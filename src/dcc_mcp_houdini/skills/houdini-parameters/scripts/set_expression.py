"""Set a channel expression on a Houdini parameter."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _parm_common import get_node  # noqa: E402


def set_expression(
    node_path: str,
    parm_name: str,
    expression: str,
    language: str = "hscript",
) -> dict:
    """Set an expression on a parm using the given language (hscript|python)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parm = node.parm(parm_name)
        if parm is None:
            return skill_error(
                "Parameter not found",
                "No parameter named {!r}".format(parm_name),
                node_path=node.path(),
            )
        lang_map = {
            "hscript": hou.exprLanguage.Hscript,
            "python": hou.exprLanguage.Python,
        }
        lang = lang_map.get(language.lower())
        if lang is None:
            return skill_error(
                "Unsupported language",
                "language must be 'hscript' or 'python'",
                requested=language,
            )
        parm.setExpression(expression, language=lang)
        return skill_success(
            "Set expression",
            node_path=node.path(),
            parm=parm_name,
            language=language.lower(),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set expression")


@skill_entry
def main(**kwargs) -> dict:
    return set_expression(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
