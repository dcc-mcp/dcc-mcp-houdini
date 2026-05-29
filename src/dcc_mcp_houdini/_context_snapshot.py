"""Houdini context snapshot provider for gateway routing and REST ``/v1/context``.

Mirrors :mod:`dcc_mcp_maya.context_snapshot`.  Feeds Houdini-specific live
scene state (hip file, frame range, object count, version) into core's
post-tool ``append_context_snapshot`` helper and into
:meth:`DccServerBase.update_gateway_metadata`.

Design
------
* :class:`HoudiniContextSnapshotProvider` is a callable that returns a fresh
  context dict on every invocation.  It is **small**, **pure**, and tolerant
  of a missing ``hou`` module: in standalone / headless / subprocess contexts
  it returns a minimal stub instead of crashing.
* :func:`collect_gateway_metadata` returns the subset consumed by
  :meth:`DccServerBase.update_gateway_metadata` (scene / version / documents /
  display_name).

Both helpers obey *Single Responsibility* — they only collect state.  They
never mutate Houdini, and they never raise.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "HoudiniContextSnapshotProvider",
    "collect_gateway_metadata",
    "make_snapshot_provider",
]


class HoudiniContextSnapshotProvider:
    """Callable returning a fresh Houdini context snapshot.

    Register with
    :meth:`dcc_mcp_core.server_base.DccServerBase.set_context_snapshot_provider`
    so the core post-tool wrapper can append ``context.houdini`` to every
    result envelope.

    Parameters
    ----------
    hou_provider:
        Optional factory returning the ``hou`` module (or a duck-typed
        stand-in for tests).  Defaults to a lazy import of ``hou`` with a
        headless-safe fallback.
    """

    def __init__(self, hou_provider: Optional[Callable[[], Any]] = None) -> None:
        self._hou_provider = hou_provider or _default_hou_provider

    # ------------------------------------------------------------------ API

    def __call__(self) -> Dict[str, Any]:
        return self.collect()

    def collect(self) -> Dict[str, Any]:
        """Return a fresh context snapshot dict.

        Keys (all optional — omitted when unavailable)::

            {
                "dcc":          "houdini",
                "scene":        "/path/to/current.hip",
                "scene_saved":  True | False,
                "frame":        1001,
                "frame_range":  [1001, 1100],
                "obj_node_count": 12,
                "display_name": "Houdini 20.5 — shot.hip",
                "version":      "20.5.445",
                "pid":          12345,
                "available":    True | False,
            }

        The method never raises; ``hou`` probes are guarded so headless /
        standalone contexts return ``{"dcc": "houdini", "available": False}``.
        """
        snapshot: Dict[str, Any] = {
            "dcc": "houdini",
            "pid": os.getpid(),
            "available": False,
        }

        hou = self._safe_hou()
        if hou is None:
            return snapshot

        snapshot["available"] = True

        # Scene (hip) path ---------------------------------------------------
        scene = _safe(lambda: hou.hipFile.path())
        has_file = _safe(lambda: bool(hou.hipFile.hasFile()))
        if scene and has_file:
            snapshot["scene"] = scene
        modified = _safe(lambda: bool(hou.hipFile.hasUnsavedChanges()))
        if modified is not None:
            snapshot["scene_saved"] = not modified

        # Timeline -----------------------------------------------------------
        frame = _safe(lambda: hou.frame())
        if frame is not None:
            try:
                snapshot["frame"] = int(frame)
            except (TypeError, ValueError):
                pass

        play_range = _safe(lambda: hou.playbar.playbackRange())
        if play_range is not None:
            try:
                snapshot["frame_range"] = [int(play_range[0]), int(play_range[1])]
            except (TypeError, ValueError, IndexError):
                pass

        # Object count -------------------------------------------------------
        obj_count = _safe(lambda: len(hou.node("/obj").children()) if hou.node("/obj") is not None else 0)
        if obj_count is not None:
            snapshot["obj_node_count"] = int(obj_count)

        # Version ------------------------------------------------------------
        version = _safe(lambda: hou.applicationVersionString())
        if version:
            snapshot["version"] = str(version)

        display = _derive_display_name(snapshot.get("scene"), snapshot.get("version"))
        if display:
            snapshot["display_name"] = display

        return snapshot

    # ------------------------------------------------------------ internals

    def _safe_hou(self) -> Any:
        try:
            return self._hou_provider()
        except Exception as exc:  # noqa: BLE001
            logger.debug("HoudiniContextSnapshotProvider: hou unavailable: %s", exc)
            return None


def collect_gateway_metadata(
    provider: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Optional[Any]]:
    """Return a subset snapshot suitable for :meth:`update_gateway_metadata`.

    Returns a dict with keys ``scene`` / ``version`` / ``documents`` /
    ``display_name``.  Houdini is a single-document DCC, so ``documents`` is
    ``[scene]`` when a hip file is open, otherwise ``[]``.
    """
    if provider is None:
        provider = HoudiniContextSnapshotProvider()
    snapshot = provider() or {}
    scene = snapshot.get("scene")
    documents: Optional[List[str]] = [scene] if scene else []
    return {
        "scene": scene if scene else None,
        "version": snapshot.get("version"),
        "documents": documents,
        "display_name": snapshot.get("display_name"),
    }


def make_snapshot_provider(
    hou_provider: Optional[Callable[[], Any]] = None,
) -> HoudiniContextSnapshotProvider:
    """Factory for a :class:`HoudiniContextSnapshotProvider`."""
    return HoudiniContextSnapshotProvider(hou_provider=hou_provider)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _default_hou_provider() -> Any:
    """Return the ``hou`` module when available, else ``None``."""
    try:
        import hou  # noqa: PLC0415

        return hou
    except Exception:  # noqa: BLE001 — headless / non-Houdini interpreter
        return None


def _safe(fn: Callable[[], Any]) -> Any:
    """Invoke ``fn`` swallowing any exception, returning ``None`` on failure."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — hou raises hou.OperationFailed etc.
        logger.debug("HoudiniContextSnapshot: probe raised %s", exc)
        return None


def _derive_display_name(scene: Optional[str], version: Optional[str]) -> Optional[str]:
    """Produce a human-readable instance label for gateway disambiguation."""
    if scene:
        try:
            basename = os.path.basename(scene) or scene
        except Exception:  # noqa: BLE001
            basename = scene
        if version:
            return "Houdini {} — {}".format(version, basename)
        return "Houdini — {}".format(basename)
    if version:
        return "Houdini {}".format(version)
    return None
