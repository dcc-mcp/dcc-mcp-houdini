"""Adopt the shared core ``qt-ui-inspector`` skill in Houdini.

Mirrors :mod:`dcc_mcp_maya._qt_inspector`.  ``dcc-mcp-core`` ships a
DCC-agnostic, read-only Qt UI inspector (``register_qt_ui_inspector``) exposing
five tools — ``list_windows``, ``find_widgets``, ``describe_widget``,
``snapshot_tree``, ``wait_for_widget``.  Houdini uses PySide2 / PySide6, so
these let agents locate panes, dialogs, buttons, tree/table views, etc. **by
text / objectName / class / accessibleName** instead of generating ad-hoc
PySide enumeration scripts through ``execute_python``.

Two Houdini-specific concerns are handled here:

* **Main-thread affinity.** ``QApplication.allWidgets()`` /
  ``topLevelWidgets()`` must be read on Houdini's UI thread.  MCP tool handlers
  run on a tokio worker thread, so each inspector handler is wrapped to marshal
  onto Houdini's main thread via the host dispatcher (the same queue
  ``execute_python`` uses).  In headless ``hython`` / pytest the wrapper runs
  inline.
* **Clear capability message.** The core tools already return structured
  ``qt-binding-unavailable`` / ``qt-no-application`` envelopes when Qt or a
  running ``QApplication`` is missing.

Operator opt-out: ``DCC_MCP_HOUDINI_QT_UI_INSPECTOR=0``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from dcc_mcp_houdini._env import ENV_QT_UI_INSPECTOR, resolve_qt_ui_inspector_enabled

logger = logging.getLogger(__name__)

_DCC_NAME = "houdini"

__all__ = [
    "ENV_QT_UI_INSPECTOR",
    "register_houdini_qt_ui_inspector",
    "resolve_qt_ui_inspector_enabled",
]


def _on_main_thread() -> bool:
    """Best-effort check whether we are already on the interpreter main thread.

    In interactive Houdini, the host pump drains queued callables on Houdini's
    main thread (the Python main thread).  MCP handlers run on tokio worker
    threads, so this guard prevents a deadlock when a handler is somehow already
    executing on the main thread.
    """
    return threading.current_thread() is threading.main_thread()


def _make_marshaller(dispatcher: Any) -> Callable[[Callable[[], Any]], Any]:
    """Return a callable that runs ``fn`` on Houdini's main thread.

    Falls back to inline execution when already on the main thread, when no
    dispatcher is available (headless ``hython`` / pytest), or when the
    dispatcher cannot marshal.
    """

    def _marshal(fn: Callable[[], Any]) -> Any:
        if dispatcher is None or _on_main_thread():
            return fn()
        dispatch = getattr(dispatcher, "dispatch_callable", None)
        if not callable(dispatch):
            return fn()
        try:
            return dispatch(fn, affinity="main", action_name="qt_ui_inspector", execution="sync")
        except Exception as exc:  # noqa: BLE001 — degrade to inline rather than fail the call
            logger.debug("[houdini] qt inspector main-thread marshalling failed, running inline: %s", exc)
            return fn()

    return _marshal


def _wrap_main_thread(
    handler: Callable[[Any], Any], marshal: Callable[[Callable[[], Any]], Any]
) -> Callable[[Any], Any]:
    def wrapper(params: Any) -> Any:
        return marshal(lambda: handler(params))

    return wrapper


class _MainThreadHandlerProxy:
    """Server proxy that wraps every registered handler in main-thread routing.

    ``register_qt_ui_inspector`` uses only ``server.registry`` and
    ``server.register_handler`` — both are forwarded; ``register_handler``
    additionally wraps the handler so the read happens on Houdini's UI thread.
    """

    def __init__(self, inner_server: Any, marshal: Callable[[Callable[[], Any]], Any]) -> None:
        self._server = inner_server
        self._marshal = marshal

    @property
    def registry(self) -> Any:
        return self._server.registry

    def register_handler(self, name: str, handler: Callable[[Any], Any]) -> Any:
        return self._server.register_handler(name, _wrap_main_thread(handler, self._marshal))

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - passthrough
        return getattr(self._server, item)


def register_houdini_qt_ui_inspector(
    server: Any,
    *,
    dcc_name: str = _DCC_NAME,
    dispatcher: Any = None,
) -> bool:
    """Register the shared ``qt_ui_inspector__*`` tools on the inner MCP server.

    Parameters
    ----------
    server:
        The :class:`HoudiniMcpServer` wrapper (exposes ``_server`` and, when
        available, ``_houdini_dispatcher``).
    dcc_name:
        DCC name tag for the core registration.
    dispatcher:
        Optional explicit host dispatcher used for main-thread marshalling.
        Defaults to ``server._houdini_dispatcher``.

    Returns ``True`` when the core inspector was registered, ``False`` when
    disabled by env var or unavailable in the installed core.
    """
    if not resolve_qt_ui_inspector_enabled():
        logger.info("[%s] qt-ui-inspector disabled via %s", dcc_name, ENV_QT_UI_INSPECTOR)
        return False

    inner = getattr(server, "_server", None)
    if inner is None:
        logger.debug("[%s] qt-ui-inspector: no inner server; skipping", dcc_name)
        return False

    try:
        from dcc_mcp_core.skills.qt_ui_inspector import register_qt_ui_inspector  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 — older core without the shared skill
        logger.info("[%s] qt-ui-inspector unavailable in installed dcc-mcp-core: %s", dcc_name, exc)
        return False

    if dispatcher is None:
        dispatcher = getattr(server, "_houdini_dispatcher", None)
    marshal = _make_marshaller(dispatcher)

    try:
        register_qt_ui_inspector(_MainThreadHandlerProxy(inner, marshal), dcc_name=dcc_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] qt-ui-inspector registration failed: %s", dcc_name, exc)
        return False
    logger.info("[%s] qt-ui-inspector tools registered (main-thread routed)", dcc_name)
    return True
