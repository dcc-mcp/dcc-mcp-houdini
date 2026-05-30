"""Houdini resource publishing wiring.

Mirrors :mod:`dcc_mcp_maya._resources`.  Core ships
``McpHttpServer.resources()`` → ``ResourceHandle`` with ``set_scene`` /
``register_producer`` / ``notify_updated``.  ``scene://current`` is a built-in
resource URI that returns ``status: no_scene_published`` until the embedding
adapter calls ``set_scene(...)``.  This module is that adapter for Houdini.

Public surface:

* :class:`HoudiniResourceBinder` — composes a Houdini scene-snapshot publisher
  (``scene://current``) plus an optional ``houdini-help://<nodetype>`` producer.
* :func:`install_resources(server)` — one-shot helper invoked from
  :meth:`HoudiniMcpServer.register_builtin_actions`.

SOLID notes
-----------
* **Single Responsibility** — each producer is a pure function from URI to
  ``{"mimeType", "text"}``; the binder only orchestrates registration and
  scene-snapshot lifetime.
* **Open/Closed** — the snapshot source and the hip-event installer are
  injectable, so tests can drive the throttling state machine without a live
  Houdini.
* **Dependency Inversion** — every Houdini-specific call (``hou``) is
  lazy-imported inside the producer body so the module is importable in plain
  Python.

Operator opt-out: ``DCC_MCP_HOUDINI_RESOURCES=0``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from dcc_mcp_houdini._env import ENV_RESOURCES, resolve_resources_enabled

logger = logging.getLogger(__name__)

#: Throttle for ``scene://current`` republishing.
DEFAULT_SCENE_THROTTLE_SECS: float = 0.5

#: Houdini-specific dynamic resource URI scheme for node-type help.
SCHEME_HOUDINI_HELP = "houdini-help://"

__all__ = [
    "ENV_RESOURCES",
    "DEFAULT_SCENE_THROTTLE_SECS",
    "SCHEME_HOUDINI_HELP",
    "HoudiniResourceBinder",
    "install_resources",
    "resolve_enabled",
]


# ``resolve_enabled`` kept as a module-level alias for parity with Maya tests.
resolve_enabled = resolve_resources_enabled


# ---------------------------------------------------------------------------
# Producer callables — pure functions, lazy hou import
# ---------------------------------------------------------------------------


def _read_text(text: str, mime: str = "text/plain") -> Dict[str, Any]:
    """Build the ``{"mimeType", "text"}`` reply expected by core."""
    return {"mimeType": mime, "text": text}


def _hou():
    """Lazy ``hou`` import; returns ``None`` outside Houdini."""
    try:
        import hou  # noqa: PLC0415

        return hou
    except Exception:  # noqa: BLE001
        return None


def _parse_path_uri(uri: str, *, scheme: str) -> Optional[List[str]]:
    """Strip *scheme* prefix and split the rest on ``/`` (empty parts skipped)."""
    if not uri.startswith(scheme):
        return None
    tail = uri[len(scheme) :]
    return [p for p in tail.split("/") if p]


def _houdini_help_producer(uri: str) -> Dict[str, Any]:
    """Producer for ``houdini-help://<category>/<nodetype>`` URIs.

    Returns the node type's help text via ``hou.nodeType(...).help()`` when
    available.  When ``hou`` is unavailable (headless/non-Houdini) or the type
    cannot be resolved, returns a JSON envelope so agents degrade gracefully.

    URI grammar:
        ``houdini-help://<nodetype>``                — search common categories
        ``houdini-help://<category>/<nodetype>``     — explicit category
    """
    parsed = _parse_path_uri(uri, scheme=SCHEME_HOUDINI_HELP)
    if not parsed:
        return _read_text(
            json.dumps({"status": "invalid_uri", "uri": uri, "hint": "houdini-help://<category>/<nodetype>"}),
            mime="application/json",
        )

    hou = _hou()
    if hou is None:
        return _read_text(
            json.dumps({"status": "houdini_unavailable", "uri": uri}),
            mime="application/json",
        )

    if len(parsed) >= 2:
        categories = [parsed[0]]
        type_name = parsed[1]
    else:
        categories = ["Sop", "Object", "Driver", "Dop", "Cop2", "Vop", "Lop", "Top"]
        type_name = parsed[0]

    try:
        node_type = _resolve_node_type(hou, categories, type_name)
    except Exception as exc:  # noqa: BLE001
        return _read_text(
            json.dumps({"status": "error", "node_type": type_name, "error": str(exc)}),
            mime="application/json",
        )
    if node_type is None:
        return _read_text(
            json.dumps({"status": "node_type_not_found", "node_type": type_name}),
            mime="application/json",
        )
    try:
        text = node_type.help()
    except Exception as exc:  # noqa: BLE001
        return _read_text(
            json.dumps({"status": "help_unavailable", "node_type": type_name, "error": str(exc)}),
            mime="application/json",
        )
    return _read_text(text or "(no help text)")


def _resolve_node_type(hou: Any, categories: List[str], type_name: str) -> Any:
    """Return the first matching ``hou.NodeType`` across *categories*, or None."""
    for category in categories:
        cat_fn = getattr(hou, "{}NodeTypeCategory".format(category), None)
        if cat_fn is None:
            # Fall back to hou.nodeType("<category>/<type>") form.
            node_type = _safe_node_type(hou, "{}/{}".format(category.lower(), type_name))
            if node_type is not None:
                return node_type
            continue
        try:
            node_type = hou.nodeType(cat_fn(), type_name)
        except Exception:  # noqa: BLE001
            node_type = None
        if node_type is not None:
            return node_type
    return None


def _safe_node_type(hou: Any, path: str) -> Any:
    try:
        return hou.nodeType(path)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Hip-file event installer (default uses hou.hipFile.addEventCallback)
# ---------------------------------------------------------------------------


SnapshotProvider = Callable[[], Dict[str, Any]]
EventInstaller = Callable[[Callable[[], None]], List[Any]]
EventRemover = Callable[[List[Any]], None]
BusyChecker = Callable[[], bool]


def _default_event_installer(callback: Callable[[], None]) -> List[Any]:
    """Register a Houdini hip-file event callback wrapping *callback*.

    Returns a list of opaque handles for cleanup.  Best-effort: a missing
    ``hou`` produces an empty list (headless mode).
    """
    hou = _hou()
    if hou is None:
        return []

    def _wrapper(*_args: Any, **_kwargs: Any) -> None:
        callback()

    try:
        hou.hipFile.addEventCallback(_wrapper)
    except Exception as exc:  # noqa: BLE001
        logger.debug("resources: hipFile.addEventCallback refused: %s", exc)
        return []
    return [_wrapper]


def _default_event_remover(handles: List[Any]) -> None:
    """Tear down callbacks installed by :func:`_default_event_installer`."""
    hou = _hou()
    if hou is None:
        return
    for handle in handles:
        try:
            hou.hipFile.removeEventCallback(handle)
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: hipFile.removeEventCallback failed: %s", exc)


# ---------------------------------------------------------------------------
# Houdini-side binder
# ---------------------------------------------------------------------------


class HoudiniResourceBinder:
    """Compose every ``server._server.resources()`` call for Houdini.

    Lifecycle::

        binder = HoudiniResourceBinder()
        binder.bind(server)             # registers producers + scene snapshot
        binder.install_scene_events()   # opt-in hip-file callback
        # ... server runs ...
        binder.unbind()                 # detach callbacks
    """

    def __init__(
        self,
        *,
        snapshot_provider: Optional[SnapshotProvider] = None,
        event_installer: Optional[EventInstaller] = None,
        event_remover: Optional[EventRemover] = None,
        busy_checker: Optional[BusyChecker] = None,
        throttle_secs: float = DEFAULT_SCENE_THROTTLE_SECS,
    ) -> None:
        self.snapshot_provider: Optional[SnapshotProvider] = snapshot_provider
        self.event_installer: EventInstaller = event_installer or _default_event_installer
        self.event_remover: EventRemover = event_remover or _default_event_remover
        self.busy_checker: Optional[BusyChecker] = busy_checker
        self.throttle_secs: float = max(0.0, float(throttle_secs))

        self.bound_server: Any = None
        self.handle: Any = None
        self.registered_producers: List[str] = []
        self.scene_event_handles: List[Any] = []
        self.scene_publish_count: int = 0

        self._lock = threading.Lock()
        self._pending_publish: bool = False
        self._last_publish_at: float = 0.0
        self._publish_timer: Optional[threading.Timer] = None
        self._unbound: bool = False

    # ── Public API ──────────────────────────────────────────────────────

    def bind(self, server: Any) -> bool:
        """Bind the binder to *server*; returns ``True`` on success."""
        if self.bound_server is server:
            return True
        self.bound_server = server
        self._unbound = False

        try:
            self.handle = server._server.resources()
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: server.resources() unavailable: %s", exc)
            return False

        self._register_producer(SCHEME_HOUDINI_HELP, _houdini_help_producer)

        if self.snapshot_provider is not None:
            self._publish_scene_now()
        return True

    def install_scene_events(self) -> List[Any]:
        """Hook hip-file events so scene mutations republish ``scene://current``."""
        if self.bound_server is None:
            return []
        if self.scene_event_handles:
            return list(self.scene_event_handles)
        handles = self.event_installer(self._on_scene_event)
        self.scene_event_handles = list(handles)
        return list(self.scene_event_handles)

    def unbind(self) -> None:
        """Detach callbacks and stop pending publishes.  Idempotent."""
        if self._unbound:
            return
        self._unbound = True

        with self._lock:
            timer = self._publish_timer
            self._publish_timer = None
            self._pending_publish = False
        if timer is not None:
            try:
                timer.cancel()
            except Exception:  # noqa: BLE001
                pass

        if self.scene_event_handles:
            try:
                self.event_remover(self.scene_event_handles)
            except Exception as exc:  # noqa: BLE001
                logger.debug("resources: event remover raised: %s", exc)
            self.scene_event_handles = []

    def publish_scene(self, payload: Optional[Dict[str, Any]] = None) -> None:
        """Publish a scene snapshot now, bypassing throttling."""
        if self.handle is None:
            return
        if payload is None:
            if self.snapshot_provider is None:
                return
            try:
                payload = self.snapshot_provider()
            except Exception as exc:  # noqa: BLE001
                logger.debug("resources: snapshot provider raised: %s", exc)
                return
        try:
            self.handle.set_scene(payload)
            self.scene_publish_count += 1
            self._last_publish_at = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: set_scene raised: %s", exc)

    # ── Internals ───────────────────────────────────────────────────────

    def _register_producer(self, scheme: str, producer: Callable[[str], Dict[str, Any]]) -> None:
        if self.handle is None:
            return
        try:
            self.handle.register_producer(scheme, producer)
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: register_producer(%s) raised: %s", scheme, exc)
            return
        self.registered_producers.append(scheme)

    def _is_executor_busy(self) -> bool:
        if self.busy_checker is None:
            return False
        try:
            return bool(self.busy_checker())
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: busy checker raised: %s", exc)
            return False

    def _on_scene_event(self) -> None:
        """Hip-event callback: schedule a throttled scene republish."""
        if self._unbound or self._is_executor_busy():
            return
        with self._lock:
            now = time.monotonic()
            since = now - self._last_publish_at
            if since >= self.throttle_secs:
                schedule_now = True
                self._pending_publish = False
            else:
                schedule_now = False
                if not self._pending_publish:
                    delay = self.throttle_secs - since
                    self._pending_publish = True
                    self._publish_timer = threading.Timer(delay, self._on_throttle_fire)
                    self._publish_timer.daemon = True
                    self._publish_timer.start()
        if schedule_now:
            self._publish_scene_now()

    def _on_throttle_fire(self) -> None:
        """Trailing-edge throttle handler — runs on a Timer thread."""
        if self._unbound or self._is_executor_busy():
            return
        with self._lock:
            self._pending_publish = False
            self._publish_timer = None
        self._publish_scene_now()

    def _publish_scene_now(self) -> None:
        self.publish_scene()
        self._sync_gateway_scene_metadata()

    def _sync_gateway_scene_metadata(self) -> None:
        """Push scene path / version into the gateway registry (best effort)."""
        server = self.bound_server
        if server is None:
            return
        publish = getattr(server, "publish_capability_snapshot", None)
        if publish is None:
            return
        try:
            publish(reason="scene_resource")
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: publish_capability_snapshot failed: %s", exc)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def install_resources(
    server: Any,
    *,
    enabled: Optional[bool] = None,
    snapshot_provider: Optional[SnapshotProvider] = None,
    install_scene_events: bool = True,
    busy_checker: Optional[BusyChecker] = None,
    throttle_secs: float = DEFAULT_SCENE_THROTTLE_SECS,
) -> Optional[HoudiniResourceBinder]:
    """One-shot helper called from :meth:`HoudiniMcpServer.register_builtin_actions`.

    Returns the :class:`HoudiniResourceBinder` when installation succeeded, or
    ``None`` when resources were disabled (``DCC_MCP_HOUDINI_RESOURCES=0``) or
    the inner Rust ``McpHttpServer.resources()`` raised.
    """
    if not resolve_resources_enabled(enabled):
        logger.debug("resources: disabled via env var")
        return None
    binder = HoudiniResourceBinder(
        snapshot_provider=snapshot_provider,
        busy_checker=busy_checker,
        throttle_secs=throttle_secs,
    )
    if not binder.bind(server):
        return None
    if install_scene_events:
        binder.install_scene_events()
    return binder
