"""Houdini host adapter for dcc-mcp-core main-thread dispatch."""

from __future__ import annotations

import contextlib
import threading
from typing import Any, Callable, Optional

from dcc_mcp_core.host import BlockingDispatcher, HostAdapter

TickFn = Callable[[], Optional[float]]


class HoudiniCallableDispatcher:
    """Callable dispatcher driven by Houdini's event-loop callback."""

    def __init__(self, dispatcher: Optional[BlockingDispatcher] = None) -> None:
        self._dispatcher = dispatcher or BlockingDispatcher()

    @property
    def host_dispatcher(self) -> BlockingDispatcher:
        """Return the core queue dispatcher that Houdini's event loop drains."""
        return self._dispatcher

    def dispatch_callable(
        self,
        func: Callable[..., Any],
        *args: Any,
        affinity: str = "main",
        context: Any = None,
        action_name: str = "",
        skill_name: Optional[str] = None,
        execution: str = "sync",
        timeout_hint_secs: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Post ``func`` to Houdini's main-thread queue and wait for its result."""
        _ = (affinity, context, action_name, skill_name, execution)

        def _invoke() -> Any:
            return func(*args, **kwargs)

        handle = self._dispatcher.post(_invoke)
        return handle.wait(timeout_hint_secs)

    def tick(self, max_jobs: int):
        """Drain queued callables from Houdini's main thread."""
        return self._dispatcher.tick(max_jobs)

    def tick_blocking(self, max_jobs: int, timeout_ms: int):
        """Drain queued callables, blocking briefly while headless."""
        return self._dispatcher.tick_blocking(max_jobs, timeout_ms)

    def shutdown(self) -> None:
        """Stop accepting queued work."""
        self._dispatcher.shutdown()

    def is_shutdown(self) -> bool:
        """Return whether the underlying dispatcher is shut down."""
        return bool(self._dispatcher.is_shutdown())


class HoudiniHost(HostAdapter):
    """Drive a dcc-mcp-core dispatcher from Houdini's main thread.

    Interactive Houdini registers the core dispatcher tick with
    ``hou.ui.addEventLoopCallback``; headless ``hython`` uses the
    blocking loop from :class:`HostAdapter`.
    """

    def __init__(self, dispatcher, **kwargs) -> None:
        super().__init__(dispatcher, name=kwargs.pop("name", "houdini-host"), **kwargs)
        self._callback: Optional[Callable[[], bool]] = None
        self._tick_thread_ident: Optional[int] = None

    @property
    def tick_thread_ident(self) -> Optional[int]:
        """Thread id of the most recent Houdini event-loop tick."""
        return self._tick_thread_ident

    def is_background(self) -> bool:
        """Return whether Houdini is running without a UI (``hython`` batch)."""
        try:
            import hou  # noqa: PLC0415

            return not bool(hou.isUIAvailable())
        except ImportError:
            return True

    def attach_tick(self, tick_fn: TickFn) -> None:
        """Register ``tick_fn`` with ``hou.ui.addEventLoopCallback``."""
        import hou  # noqa: PLC0415

        def _callback() -> bool:
            self._tick_thread_ident = threading.get_ident()
            interval = tick_fn()
            return interval is not None

        self._callback = _callback
        hou.ui.addEventLoopCallback(_callback)

    def detach_tick(self) -> None:
        """Remove the Houdini event-loop callback, if still registered."""
        import hou  # noqa: PLC0415

        callback = self._callback
        if callback is not None:
            with contextlib.suppress(Exception):
                hou.ui.removeEventLoopCallback(callback)
        self._callback = None
