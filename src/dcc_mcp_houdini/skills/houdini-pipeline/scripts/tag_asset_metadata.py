"""Tag adapter-owned asset metadata on a Houdini node or the hip file."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from _pipeline_common import META_PREFIX, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def tag_asset_metadata(
    metadata: Dict[str, Any],
    node_path: Optional[str] = None,
    merge: bool = True,
) -> dict:
    """Store *metadata* as adapter-owned user data on a node or the hip file.

    Values are JSON-serialised under a stable ``dcc_mcp_meta:`` key so the
    schema stays portable and never references private production services.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not isinstance(metadata, dict) or not metadata:
            return skill_error(
                "Invalid metadata",
                "metadata must be a non-empty object",
            )
        key = META_PREFIX + "asset"
        if node_path:
            target = get_node(hou, node_path)
            getter, setter, location = target.userData, target.setUserData, target.path()
        else:
            target = hou.hipFile
            getter = lambda k: hou.hipFile.userData(k) if hasattr(hou.hipFile, "userData") else None  # noqa: E731
            setter = hou.hipFile.setUserData if hasattr(hou.hipFile, "setUserData") else None
            location = "hipFile"
            if setter is None:
                return skill_error(
                    "Hip metadata unsupported",
                    "This Houdini build has no hipFile.setUserData; pass node_path instead",
                )

        existing: Dict[str, Any] = {}
        if merge:
            try:
                raw = getter(key)
                if raw:
                    existing = json.loads(raw)
            except Exception:  # noqa: BLE001
                existing = {}
        existing.update(metadata)
        setter(key, json.dumps(existing))
        return skill_success(
            "Tagged asset metadata",
            location=location,
            keys=sorted(existing.keys()),
            merged=bool(merge),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to tag asset metadata")


@skill_entry
def main(**kwargs) -> dict:
    return tag_asset_metadata(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
