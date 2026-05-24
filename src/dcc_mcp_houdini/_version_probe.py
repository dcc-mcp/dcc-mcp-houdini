"""Houdini version detection helpers."""

from __future__ import annotations


def is_houdini_available() -> bool:
    """Return ``True`` when the ``hou`` module can be imported."""
    try:
        import hou  # noqa: PLC0415

        _ = hou
        return True
    except ImportError:
        return False


def get_houdini_version_string() -> str:
    """Return Houdini's version string, or ``"unknown"`` outside Houdini."""
    try:
        import hou  # noqa: PLC0415

        return str(hou.applicationVersionString())
    except Exception:
        return "unknown"


def get_houdini_version_tuple() -> tuple[int, ...]:
    """Return Houdini's version tuple, or ``()`` outside Houdini."""
    try:
        import hou  # noqa: PLC0415

        return tuple(int(v) for v in hou.applicationVersion())
    except Exception:
        return ()
