"""Reliable HIP file state probes across Houdini and hython."""

from __future__ import annotations

from typing import Any, Optional


def get_hip_dirty_state(hou: Any) -> Optional[bool]:
    """Return the GUI dirty state, or ``None`` when HOM cannot report it.

    SideFX documents that ``hou.hipFile.hasUnsavedChanges()`` always returns
    ``True`` in non-graphical hython sessions, so that value is not evidence of
    unsaved changes there:
    https://www.sidefx.com/docs/houdini/hom/hou/hipFile.html
    """
    try:
        if not hou.isUIAvailable():
            return None
        return bool(hou.hipFile.hasUnsavedChanges())
    except Exception:  # noqa: BLE001 -- unavailable HOM state is unknown
        return None
