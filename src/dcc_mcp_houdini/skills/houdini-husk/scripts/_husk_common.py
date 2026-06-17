"""Shared helpers for Houdini husk command-line render skills."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional, Sequence


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def set_parm_if_exists(node: Any, name: str, value: Any) -> bool:
    """Set a scalar/tuple parm only when it exists. Return whether it was set."""
    if isinstance(value, (list, tuple)):
        parm_tuple = node.parmTuple(name)
        if parm_tuple is None:
            return False
        parm_tuple.set(tuple(value))
        return True
    parm = node.parm(name)
    if parm is None:
        return False
    parm.set(value)
    return True


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def find_husk() -> Optional[str]:
    """Locate the husk executable on PATH or in Houdini bin directory."""
    # Try direct PATH lookup
    husk_path = shutil.which("husk")
    if husk_path:
        return husk_path

    # Try common Houdini locations
    hfs = os.environ.get("HFS", "")
    if hfs:
        candidate = os.path.join(hfs, "bin", "husk")
        if os.path.isfile(candidate):
            return candidate
        # Windows variant
        candidate_exe = os.path.join(hfs, "bin", "husk.exe")
        if os.path.isfile(candidate_exe):
            return candidate_exe

    return None


def find_hython() -> Optional[str]:
    """Locate hython on PATH or in Houdini bin directory."""
    hython_path = shutil.which("hython")
    if hython_path:
        return hython_path

    hfs = os.environ.get("HFS", "")
    if hfs:
        candidate = os.path.join(hfs, "bin", "hython")
        if os.path.isfile(candidate):
            return candidate
        candidate_exe = os.path.join(hfs, "bin", "hython.exe")
        if os.path.isfile(candidate_exe):
            return candidate_exe

    return None


def build_husk_command(
    usd_file: str,
    output_path: str,
    frame: Optional[int] = None,
    frame_range: Optional[Sequence[float]] = None,
    renderer: str = "karma",
    resolution: Optional[Sequence[int]] = None,
    extra_args: Optional[list] = None,
) -> list:
    """Build a husk command-line argument list."""
    cmd = ["husk"]

    if renderer:
        cmd.extend(["--renderer", renderer])

    if resolution and len(resolution) >= 2:
        cmd.extend(["--res", str(int(resolution[0])), str(int(resolution[1]))])

    if frame_range and len(frame_range) >= 2:
        cmd.extend(["--frame", str(float(frame_range[0])), str(float(frame_range[1]))])
    elif frame is not None:
        cmd.extend(["--frame", str(int(frame))])

    if output_path:
        cmd.extend(["--output", output_path])

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(usd_file)
    return cmd
