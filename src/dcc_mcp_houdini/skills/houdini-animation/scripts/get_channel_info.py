"""Inspect a channel: expression, keyframe count, time dependence, value."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _anim_common import get_node, get_parm  # noqa: E402


def get_channel_info(node_path: str, parm_name: str) -> dict:
    """Return expression/keyframe/time-dependence info for a parameter."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parm = get_parm(node, parm_name)
        expression = None
        language = None
        try:
            expression = parm.expression()
            lang = parm.expressionLanguage()
            language = lang.name() if hasattr(lang, "name") else str(lang)
        except Exception:  # noqa: BLE001 - no expression set
            expression = None
        try:
            keyframe_count = len(parm.keyframes())
        except Exception:  # noqa: BLE001
            keyframe_count = None
        try:
            is_time_dependent = bool(parm.isTimeDependent())
        except Exception:  # noqa: BLE001
            is_time_dependent = None
        try:
            value = parm.eval()
        except Exception:  # noqa: BLE001
            value = None
        return skill_success(
            "Read channel info",
            node_path=node.path(),
            parm=parm_name,
            expression=expression,
            language=language,
            keyframe_count=keyframe_count,
            is_time_dependent=is_time_dependent,
            value=value,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read channel info")


@skill_entry
def main(**kwargs) -> dict:
    return get_channel_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
