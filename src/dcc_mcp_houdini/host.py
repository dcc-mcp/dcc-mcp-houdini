"""Houdini host adapter for dcc-mcp-core main-thread dispatch."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
import uuid
from typing import Any, Callable, Optional

from dcc_mcp_core import HostPumpController, HostUiDispatcherBase
from dcc_mcp_core.host import BlockingDispatcher, HostAdapter

TickFn = Callable[[], Optional[float]]
logger = logging.getLogger(__name__)


class HoudiniEventLoopTimerAdapter:
    """Adapt Houdini's single event-loop callback to the core pump timer."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        error_retry_secs: float = 0.05,
        pre_drain_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        if error_retry_secs <= 0:
            raise ValueError("error_retry_secs must be > 0")
        self._clock = clock
        self._error_retry_secs = float(error_retry_secs)
        self._lock = threading.Lock()
        self._tick: Optional[TickFn] = None
        self._callback: Optional[Callable[[], None]] = None
        self._next_due = 0.0
        self._tick_thread_ident: Optional[int] = None
        self._pre_drain_check = pre_drain_check

    @property
    def installed(self) -> bool:
        """Return whether the Houdini callback is registered."""
        with self._lock:
            return self._callback is not None

    @property
    def tick_thread_ident(self) -> Optional[int]:
        """Thread id of the most recent due event-loop tick."""
        return self._tick_thread_ident

    def install(self, tick: TickFn) -> None:
        """Install exactly one Houdini event-loop callback."""
        import hou  # noqa: PLC0415

        with self._lock:
            self._tick = tick
            self._next_due = 0.0
            if self._callback is not None:
                return

            def _callback() -> None:
                now = self._clock()
                with self._lock:
                    due_tick = self._tick
                    if due_tick is None or now < self._next_due:
                        return
                    self._next_due = float("inf")

                # Pre-drain validity check: skip this tick if the Houdini
                # scene is no longer available (e.g. session closed, node
                # graph destroyed).  This prevents pump drain from touching
                # stale hou.Parm references whose backing HOM objects have
                # been freed, which would trigger a native SIGSEGV.
                #
                # When the check fails we MUST reset _next_due under the
                # lock — otherwise it stays at inf (set on entry at L67)
                # and the pump is permanently wedged with queued jobs
                # never drained.  A short retry interval keeps the pump
                # alive while avoiding a tight spin on a dead scene.
                pre_check = self._pre_drain_check
                if pre_check is not None:
                    try:
                        ok = pre_check()
                    except Exception:  # noqa: BLE001
                        logger.warning("Pre-drain validity check failed; skipping tick")
                        ok = False
                    if not ok:
                        with self._lock:
                            self._next_due = now + self._error_retry_secs
                        return

                self._tick_thread_ident = threading.get_ident()
                try:
                    interval = due_tick()
                except Exception:  # noqa: BLE001
                    logger.exception("Houdini host pump tick failed")
                    interval = self._error_retry_secs

                if interval is None:
                    self.uninstall()
                    return
                with self._lock:
                    if self._tick is not None and self._next_due != 0.0:
                        self._next_due = self._clock() + max(float(interval), 0.0)

            self._callback = _callback

        try:
            hou.ui.addEventLoopCallback(_callback)
        except Exception:
            with self._lock:
                self._callback = None
                self._tick = None
            raise

    def uninstall(self) -> None:
        """Remove the registered callback, if any."""
        with self._lock:
            callback = self._callback
            self._callback = None
            self._tick = None
            self._next_due = 0.0
        if callback is None:
            return
        with contextlib.suppress(Exception):
            import hou  # noqa: PLC0415

            hou.ui.removeEventLoopCallback(callback)

    def schedule_soon(self) -> None:
        """Make the already-registered callback drain on its next invocation."""
        with self._lock:
            if self._callback is not None:
                self._next_due = 0.0


class HoudiniUiDispatcher(HostUiDispatcherBase):
    """Thin Houdini wrapper around the shared core UI dispatcher."""

    def __init__(self) -> None:
        super().__init__(label="houdini-ui")
        self._owner_thread_ident = threading.get_ident()
        self._pump_controller: Optional[HostPumpController] = None

    def attach_pump_controller(self, controller: HostPumpController) -> None:
        """Attach the controller that schedules Houdini event-loop ticks."""
        self._pump_controller = controller

    def detach_pump_controller(self, controller: Optional[HostPumpController] = None) -> None:
        """Detach a stopped controller without disturbing a replacement."""
        if controller is None or self._pump_controller is controller:
            self._pump_controller = None

    def poke_host_pump(self) -> None:
        """Ask the existing Houdini callback to drain queued work soon."""
        controller = self._pump_controller
        if controller is not None:
            controller.schedule_soon()

    def is_host_thread(self) -> bool:
        """Recognise both the construction thread and observed pump thread."""
        return threading.get_ident() == self._owner_thread_ident or super().is_host_thread()

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
        """Run ``func`` through the shared UI-thread job lifecycle."""
        _ = (context, execution)
        if (affinity or "main").lower() == "main" and self.is_host_thread():
            return func(*args, **kwargs)

        label = ".".join(part for part in (skill_name, action_name) if part) or "houdini-call"
        request_id = f"{label}:{uuid.uuid4().hex}"
        timeout_ms = timeout_hint_secs * 1000 if timeout_hint_secs and timeout_hint_secs > 0 else None
        outcome = self.submit_callable(
            request_id,
            lambda: func(*args, **kwargs),
            affinity=affinity,
            timeout_ms=timeout_ms,
        )
        if outcome.get("success"):
            return outcome.get("output")
        raise RuntimeError(outcome.get("error") or "Houdini UI dispatch failed")


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

    def submit_async_callable(
        self,
        request_id: str,
        task: Callable[[], Any],
        *,
        job_id: Optional[str] = None,
        progress_token: Optional[str] = None,
        on_complete: Optional[Callable[[dict], None]] = None,
        affinity: str = "main",
        timeout_ms: Optional[int] = None,
    ) -> dict:
        """Queue a readiness/lifecycle probe without executing off-thread."""
        _ = (progress_token, timeout_ms)

        def _invoke() -> dict:
            try:
                result = {
                    "request_id": request_id,
                    "job_id": job_id,
                    "affinity": affinity,
                    "success": True,
                    "status": "completed",
                    "output": task(),
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 - preserve dispatcher result contract
                result = {
                    "request_id": request_id,
                    "job_id": job_id,
                    "affinity": affinity,
                    "success": False,
                    "status": "failed",
                    "output": None,
                    "error": str(exc),
                }
            if on_complete is not None:
                try:
                    on_complete(result)
                except Exception as exc:  # noqa: BLE001 - isolate lifecycle observers
                    logger.warning("Houdini headless completion callback failed: %s", exc)
            return result

        self._dispatcher.post(_invoke)
        return {
            "request_id": request_id,
            "job_id": job_id,
            "affinity": affinity,
            "success": True,
            "status": "queued",
            "output": None,
            "error": None,
        }

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


class HoudiniInlineCallableDispatcher:
    """Execute after the HTTP layer has already hopped to the host queue."""

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
        """Run inline without posting a second job to the same queue."""
        _ = (affinity, context, action_name, skill_name, execution, timeout_hint_secs)
        return func(*args, **kwargs)


class HoudiniUiPump:
    """Drive an interactive Houdini dispatcher through the core pump."""

    def __init__(
        self,
        dispatcher: HoudiniUiDispatcher,
        *,
        budget_ms: int = 8,
        timer_adapter: Optional[HoudiniEventLoopTimerAdapter] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._dispatcher = dispatcher
        if timer_adapter is None:
            timer_adapter = HoudiniEventLoopTimerAdapter(
                clock=clock,
                pre_drain_check=_make_houdini_scene_validity_check(),
            )
        self._timer = timer_adapter
        self._controller = HostPumpController(
            dispatcher,
            self._timer,
            budget_ms=budget_ms,
            clock=clock,
            shutdown_pump_on_stop=True,
        )
        dispatcher.attach_pump_controller(self._controller)

    @property
    def controller(self) -> HostPumpController:
        """Return the shared core pump controller."""
        return self._controller

    @property
    def stats(self):
        """Return queue, timing, and overrun counters."""
        return self._controller.stats

    @property
    def tick_thread_ident(self) -> Optional[int]:
        """Thread id of the most recent Houdini event-loop tick."""
        return self._timer.tick_thread_ident

    @property
    def is_running(self) -> bool:
        """Return whether the event-loop callback is installed."""
        return self._controller.is_running

    def start(self) -> None:
        """Install the pump once; repeated starts are harmless."""
        self._dispatcher.attach_pump_controller(self._controller)
        self._controller.start()

    def stop(self) -> None:
        """Stop the pump and unblock queued waiters; idempotent."""
        self._controller.stop()
        self._dispatcher.detach_pump_controller(self._controller)


class HoudiniHost(HostAdapter):
    """Legacy queue host retained for direct and headless integrations.

    New interactive server stacks use :class:`HoudiniUiPump`.  Keeping this
    adapter preserves the public ``HoudiniHost(blocking).run_headless()``
    contract used by standalone bootstrap scripts.
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

    def run_headless(self, stop_event: Optional[threading.Event] = None) -> None:
        """Pump on Hython's owning thread until shutdown is requested."""
        self._tick_thread_ident = threading.get_ident()
        super().run_headless(stop_event=stop_event)

    def attach_tick(self, tick_fn: TickFn) -> None:
        """Register ``tick_fn`` with ``hou.ui.addEventLoopCallback``."""
        import hou  # noqa: PLC0415

        def _callback() -> bool:
            self._tick_thread_ident = threading.get_ident()
            return tick_fn() is not None

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


def _make_houdini_scene_validity_check() -> Callable[[], bool]:
    """Return a callable that quickly tests whether the Houdini scene is alive.

    The check probes ``hou.node("/obj")`` — the standard root object node
    that exists in every valid Houdini session.  A ``None`` result means the
    scene graph has been torn down (session closed, catastrophic error) and
    no further pump ticks should drain queued jobs.

    When the ``hou`` module cannot be imported (tests, CI, or any non-Houdini
    environment), there is no native scene that can cause a SIGSEGV, so the
    check returns ``True`` unconditionally — the pump runs normally.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        # Outside Houdini there is no native scene to crash on — let the
        # pump run normally (tests, CI, headless linters).
        return lambda: True

    def _check() -> bool:
        try:
            return hou.node("/obj") is not None
        except Exception:  # noqa: BLE001
            return False

    return _check
