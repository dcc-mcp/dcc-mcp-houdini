"""List saved material presets (adapter-owned JSON store, read-only)."""

from __future__ import annotations

import json

from _lookdev_common import preset_dir  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def list_presets() -> dict:
    """Return saved material presets with their material type and parm counts."""
    try:
        base = preset_dir()
        presets = []
        for path in sorted(base.glob("*.json")):
            entry = {"name": path.stem, "preset_path": str(path)}
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
                entry["material_type"] = data.get("material_type")
                entry["parameter_count"] = len(data.get("parameters", {}))
            except Exception:  # noqa: BLE001
                entry["error"] = "unreadable preset"
            presets.append(entry)
        return skill_success(
            "Listed material presets",
            preset_dir=str(base),
            count=len(presets),
            presets=presets,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list material presets")


@skill_entry
def main(**kwargs) -> dict:
    return list_presets(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
