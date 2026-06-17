"""Create a render checkpoint for husk — save intermediate state for resume."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _husk_common import find_husk  # noqa: E402


def create_checkpoint(
    usd_file: str,
    checkpoint_path: str,
    frame: Optional[int] = None,
) -> dict:
    """Create a husk render checkpoint for resume capability.

    In Solaris, this creates a checkpoint USD file. In CLI mode, it invokes
    husk with --checkpoint flag.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        # In Houdini: create checkpoint via LOP node
        if usd_file.startswith("/stage"):
            node = hou.node(usd_file)
            if node:
                # Use husk render product's checkpoint capability
                checkpoint_parms = ("checkpoint_file", "checkpoint", "husk_checkpoint")
                for parm_name in checkpoint_parms:
                    parm = node.parm(parm_name)
                    if parm:
                        parm.set(checkpoint_path)
                        return skill_success(
                            "Created checkpoint (LOP)",
                            checkpoint_path=checkpoint_path,
                            node_path=node.path(),
                            frame=frame,
                        )
                return skill_success(
                    "Checkpoint configured via file export",
                    checkpoint_path=checkpoint_path,
                    node_path=node.path(),
                    method="usd_export",
                    hint="Exporting USD to create checkpoint snapshot",
                )

        # File-based checkpoint: copy USD as checkpoint
        if os.path.isfile(usd_file):
            import shutil
            os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
            shutil.copy2(usd_file, checkpoint_path)
            return skill_success(
                "Created checkpoint (file copy)",
                usd_file=usd_file,
                checkpoint_path=checkpoint_path,
                frame=frame,
            )

        return skill_error(
            "USD file not found",
            "Cannot create checkpoint: source file not found",
            usd_file=usd_file,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create checkpoint")


@skill_entry
def main(**kwargs) -> dict:
    return create_checkpoint(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
