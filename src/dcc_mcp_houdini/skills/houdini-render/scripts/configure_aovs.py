"""Configure AOVs (Arbitrary Output Variables) on a render node or Solaris product."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _render_common import get_node, node_summary, set_first_parm  # noqa: E402

# Common AOV presets with their source names
AOV_PRESETS = {
    "diffuse": {"source": "diffuse", "type": "color"},
    "specular": {"source": "specular", "type": "color"},
    "transmission": {"source": "transmission", "type": "color"},
    "normal": {"source": "normal", "type": "vector"},
    "depth": {"source": "depth", "type": "float"},
    "motionvector": {"source": "motionvector", "type": "vector"},
    "albedo": {"source": "albedo", "type": "color"},
    "opacity": {"source": "opacity", "type": "color"},
    "emission": {"source": "emission", "type": "color"},
    "volume": {"source": "volume", "type": "color"},
    "cryptomatte": {"source": "cryptomatte", "type": "color"},
    "objectid": {"source": "objectid", "type": "int"},
    "materialid": {"source": "materialid", "type": "int"},
    "uv": {"source": "uv", "type": "vector"},
    "worldpos": {"source": "worldpos", "type": "vector"},
}


def configure_aovs(
    rop_path: str,
    aovs: List[str],
    action: str = "add",
) -> dict:
    """Add or remove AOVs on the ROP/Solaris node at *rop_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, rop_path)
        is_solaris = rop_path.startswith("/stage")
        configured: list = []
        unsupported: list = []

        if is_solaris:
            # Solaris: iterate render vars under a render product
            for aov_name in aovs:
                if action == "remove":
                    rv_node = node.node(aov_name)
                    if rv_node:
                        rv_node.destroy()
                        configured.append({"name": aov_name, "action": "removed"})
                    else:
                        unsupported.append(aov_name)
                else:
                    preset = AOV_PRESETS.get(aov_name.lower(), {"source": aov_name, "type": "raw"})
                    rv_node = node.createNode("rendervar", node_name=aov_name)
                    set_first_parm(rv_node, ("sourceName", "sourcename"), preset["source"])
                    set_first_parm(rv_node, ("sourceType", "sourcetype"), preset["type"])
                    configured.append(
                        {
                            "name": aov_name,
                            "source": preset["source"],
                            "type": preset["type"],
                            "path": rv_node.path(),
                        }
                    )
        else:
            # Traditional ROP: attempt extra image planes
            for aov_name in aovs:
                preset = AOV_PRESETS.get(aov_name.lower(), {"source": aov_name, "type": "raw"})
                aov_key = "vm_numaux" if action == "add" else None
                if aov_key and set_first_parm(node, (aov_key,), 1):
                    configured.append(
                        {
                            "name": aov_name,
                            "action": "hint_enabled",
                            "note": "AOV enabled via vm_numaux; configure in ROP UI for exact plane names",
                        }
                    )
                else:
                    unsupported.append(aov_name)

        return skill_success(
            "Configured AOVs",
            node=node_summary(node),
            configured=configured,
            unsupported=unsupported,
            action=action,
            is_solaris=is_solaris,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure AOVs")


@skill_entry
def main(**kwargs) -> dict:
    return configure_aovs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
