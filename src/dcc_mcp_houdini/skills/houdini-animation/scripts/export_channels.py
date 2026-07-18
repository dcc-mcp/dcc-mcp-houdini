"""Export keyframe channel data for parameters to a JSON file."""

from __future__ import annotations

import json
import os
from typing import List

from _anim_common import get_node, keyframe_dict  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def export_channels(node_path: str, parm_names: List[str], output_path: str) -> dict:
    """Write a JSON channel dump for *parm_names* on *node_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        channels = {}
        warnings: List[str] = []
        for name in parm_names:
            parm = node.parm(name)
            if parm is None:
                warnings.append("No parameter named {!r}".format(name))
                continue
            channels[name] = [keyframe_dict(kf) for kf in parm.keyframes()]
        payload = {"node_path": node.path(), "channels": channels}
        parent = os.path.dirname(os.path.abspath(output_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return skill_success(
            "Exported channels",
            node_path=node.path(),
            output_path=output_path,
            channel_count=len(channels),
            written_files=[output_path] if os.path.isfile(output_path) else [],
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to export channels")


@skill_entry
def main(**kwargs) -> dict:
    return export_channels(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
