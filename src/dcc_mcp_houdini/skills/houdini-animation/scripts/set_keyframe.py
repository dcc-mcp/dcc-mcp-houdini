"""Set a keyframe (value or expression) on a node parameter at a frame."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _anim_common import get_node, get_parm  # noqa: E402


def set_keyframe(
    node_path: str,
    parm_name: str,
    frame: float,
    value: Optional[float] = None,
    expression: Optional[str] = None,
    language: str = "hscript",
) -> dict:
    """Set a keyframe on ``node_path/parm_name`` at *frame*.

    Provide ``value`` for a constant key or ``expression`` for an expression
    key (``language`` is "hscript" or "python").
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if value is None and expression is None:
        return skill_error("Nothing to set", "Provide value or expression")

    try:
        node = get_node(hou, node_path)
        parm = get_parm(node, parm_name)
        kf = hou.Keyframe()
        kf.setFrame(float(frame))
        if expression is not None:
            lang = hou.exprLanguage.Python if language.lower() == "python" else hou.exprLanguage.Hscript
            kf.setExpression(expression, lang)
        else:
            kf.setValue(float(value))
        parm.setKeyframe(kf)
        return skill_success(
            "Set keyframe",
            node_path=node.path(),
            parm=parm_name,
            frame=float(frame),
            value=value,
            expression=expression,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set keyframe")


@skill_entry
def main(**kwargs) -> dict:
    return set_keyframe(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
