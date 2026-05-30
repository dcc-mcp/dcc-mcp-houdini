"""Set display / render / template / bypass flags on a Houdini node."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _object_common import get_node  # noqa: E402

# Flag name -> setter method on the node. Only applied when the node exposes the
# setter and the caller passed a value for that flag.
_FLAG_SETTERS = {
    "display": "setDisplayFlag",
    "render": "setRenderFlag",
    "template": "setTemplateFlag",
    "bypass": "bypass",
}


def set_node_flags(
    node_path: str,
    display: Optional[bool] = None,
    render: Optional[bool] = None,
    template: Optional[bool] = None,
    bypass: Optional[bool] = None,
) -> dict:
    """Apply the supplied node flags. Unspecified (None) flags are left alone."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        requested = {
            "display": display,
            "render": render,
            "template": template,
            "bypass": bypass,
        }
        applied = {}
        unsupported = []
        for flag, value in requested.items():
            if value is None:
                continue
            setter_name = _FLAG_SETTERS[flag]
            setter = getattr(node, setter_name, None)
            if setter is None:
                unsupported.append(flag)
                continue
            setter(bool(value))
            applied[flag] = bool(value)
        if not applied and unsupported:
            return skill_error(
                "No flags applied",
                "None of the requested flags are supported on this node",
                unsupported=unsupported,
            )
        return skill_success(
            "Updated node flags",
            node_path=node.path(),
            applied=applied,
            unsupported=unsupported,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set node flags")


@skill_entry
def main(**kwargs) -> dict:
    return set_node_flags(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
