"""Configure husk command-line options for USD/Hydra rendering."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


# Known husk CLI options organized by category
HUSK_OPTIONS = {
    "render": [
        {"flag": "--renderer", "type": "string", "description": "Hydra render delegate (e.g. karma, GL)"},
        {"flag": "--render-setting", "type": "key=value", "description": "Render setting override (repeatable)"},
    ],
    "output": [
        {"flag": "--output", "type": "path", "description": "Output image path (supports $F frame token)"},
        {"flag": "--res", "type": "W H", "description": "Resolution [width height]"},
        {"flag": "--crop", "type": "x y w h", "description": "Crop window"},
        {"flag": "--exr-compression", "type": "string", "description": "EXR compression (zips, piz, etc.)"},
    ],
    "frame": [
        {"flag": "--frame", "type": "int|start end", "description": "Single frame or range"},
        {"flag": "--frame-inc", "type": "float", "description": "Frame increment for range"},
    ],
    "debug": [
        {"flag": "--verbose", "type": "flag", "description": "Verbose output"},
        {"flag": "--dryrun", "type": "flag", "description": "Dry run (no render, validate only)"},
        {"flag": "--profile", "type": "flag", "description": "Profile render"},
        {"flag": "--timing", "type": "flag", "description": "Report timing"},
    ],
    "performance": [
        {"flag": "--threads", "type": "int", "description": "CPU thread count (0 = auto)"},
        {"flag": "--gpu", "type": "flag", "description": "Enable GPU rendering"},
        {"flag": "--gpu-device", "type": "int", "description": "GPU device index"},
    ],
}


def set_husk_options(
    node_path: Optional[str] = None,
    options: Optional[dict] = None,
    list_options: bool = False,
    category: Optional[str] = None,
) -> dict:
    """Configure or inspect husk command-line rendering options.

    When *node_path* is provided, sets options on a LOP/ROP node.
    When *list_options* is true, returns the known husk CLI option catalog.
    """
    if list_options:
        if category and category in HUSK_OPTIONS:
            return skill_success(
                "Husk options (category: {})".format(category),
                category=category,
                options=HUSK_OPTIONS[category],
            )
        return skill_success(
            "Husk CLI option catalog",
            categories=list(HUSK_OPTIONS.keys()),
            options=HUSK_OPTIONS,
        )

    if node_path:
        try:
            import hou  # noqa: PLC0415
        except ImportError:
            return skill_error("Houdini not available", "hou could not be imported")

        try:
            node = hou.node(node_path)
            if node is None:
                return skill_error(
                    "Node not found",
                    "No node at path: {}".format(node_path),
                )

            applied: dict = {}
            unsupported: list = []

            if options:
                for key, value in options.items():
                    parm_names = (
                        "husk_{}".format(key),
                        "husk_{}".format(key.replace("-", "_")),
                        key,
                        key.replace("-", "_"),
                    )
                    used = False
                    for name in parm_names:
                        parm = node.parm(name)
                        if parm:
                            try:
                                parm.set(value)
                                applied[key] = value
                                used = True
                                break
                            except Exception:
                                continue
                    if not used:
                        unsupported.append(key)

            return skill_success(
                "Set husk options",
                node_path=node.path(),
                applied=applied,
                unsupported=unsupported,
            )
        except Exception as exc:
            return skill_exception(exc, message="Failed to set husk options")

    return skill_success(
        "Husk options — provide node_path to apply, or list_options=true to browse",
        categories=list(HUSK_OPTIONS.keys()),
    )


@skill_entry
def main(**kwargs) -> dict:
    return set_husk_options(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
