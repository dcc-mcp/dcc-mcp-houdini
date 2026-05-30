"""Import keyframe channel data from a JSON file onto node parameters."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _anim_common import get_node  # noqa: E402


def import_channels(input_path: str, node_path: Optional[str] = None) -> dict:
    """Apply a JSON channel dump (from export_channels) onto a node.

    The target defaults to the dump's recorded ``node_path``; pass *node_path*
    to retarget the channels onto a different node.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if not os.path.isfile(input_path):
        return skill_error("File not found", "No channel file at the given path", input_path=input_path)

    try:
        with open(input_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        channels = payload.get("channels", {})
        target_path = node_path or payload.get("node_path")
        if not target_path:
            return skill_error("No target node", "No node_path in payload or argument")
        node = get_node(hou, target_path)
        applied = {}
        warnings = []
        for name, keyframes in channels.items():
            parm = node.parm(name)
            if parm is None:
                warnings.append("No parameter named {!r}".format(name))
                continue
            count = 0
            for entry in keyframes:
                kf = hou.Keyframe()
                kf.setFrame(float(entry.get("frame", 0.0)))
                expression = entry.get("expression")
                if expression:
                    kf.setExpression(expression, hou.exprLanguage.Hscript)
                elif entry.get("value") is not None:
                    kf.setValue(float(entry["value"]))
                else:
                    continue
                parm.setKeyframe(kf)
                count += 1
            applied[name] = count
        return skill_success(
            "Imported channels",
            node_path=node.path(),
            input_path=input_path,
            applied=applied,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to import channels")


@skill_entry
def main(**kwargs) -> dict:
    return import_channels(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
