"""Read adapter-owned asset metadata from a Houdini node or the hip file."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _pipeline_common import META_PREFIX, get_node  # noqa: E402


def get_asset_metadata(node_path: Optional[str] = None) -> dict:
    """Return the ``dcc_mcp_meta:asset`` payload, or an empty mapping."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        key = META_PREFIX + "asset"
        if node_path:
            target = get_node(hou, node_path)
            raw = target.userData(key)
            location = target.path()
        else:
            getter = getattr(hou.hipFile, "userData", None)
            raw = getter(key) if callable(getter) else None
            location = "hipFile"
        metadata = {}
        if raw:
            try:
                metadata = json.loads(raw)
            except Exception:  # noqa: BLE001
                metadata = {"_raw": raw}
        return skill_success(
            "Read asset metadata",
            location=location,
            metadata=metadata,
            found=bool(metadata),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read asset metadata")


@skill_entry
def main(**kwargs) -> dict:
    return get_asset_metadata(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
