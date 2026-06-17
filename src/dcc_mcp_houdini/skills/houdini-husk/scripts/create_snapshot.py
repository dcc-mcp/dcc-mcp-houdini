"""Create a USD scene snapshot for husk rendering — export current stage state."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _husk_common import get_node  # noqa: E402


def create_snapshot(
    source_path: str = "/stage",
    snapshot_path: str = "/tmp/husk_snapshot.usd",
    flatten: bool = False,
    frame: Optional[float] = None,
) -> dict:
    """Export the current stage/LOP network as a USD snapshot for husk."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, source_path)
        is_lop = source_path.startswith("/stage")

        if is_lop:
            # Solaris LOP: use USD export or save node
            if hasattr(node, "save") and hasattr(node, "saveItems"):
                try:
                    node.saveItems([snapshot_path])
                    return skill_success(
                        "Created USD snapshot (saveItems)",
                        source=node.path(),
                        snapshot_path=snapshot_path,
                        frame=frame,
                    )
                except Exception:
                    pass

            # Try creating a USD ROP or using a save LOP
            try:
                save_lop = node.createNode("usdsave", node_name="snapshot_export")
                save_lop.parm("lopoutput").set(snapshot_path)
                if flatten:
                    save_lop.parm("flatten").set(1)
                if frame is not None:
                    save_lop.parm("trange").set(0)
                    hou.setFrame(float(frame))
                save_lop.cook()
                written = os.path.isfile(snapshot_path)
                save_lop.destroy()
                return skill_success(
                    "Created USD snapshot (usdsave LOP)",
                    source=node.path(),
                    snapshot_path=snapshot_path,
                    written=written,
                    frame=frame,
                    flatten=flatten,
                )
            except Exception as e:
                return skill_error(
                    "Snapshot creation failed",
                    "Could not create USD snapshot: {}".format(e),
                    source=source_path,
                )
        else:
            # Non-Solaris: export as .usd via ROP
            return skill_success(
                "Snapshot hint",
                source=node.path(),
                hint="Non-Solaris source — use houdini-interchange export_usd to create a USD snapshot",
                suggested_snapshot=snapshot_path,
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create snapshot")


@skill_entry
def main(**kwargs) -> dict:
    return create_snapshot(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
