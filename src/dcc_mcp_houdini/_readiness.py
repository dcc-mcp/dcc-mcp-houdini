"""Runtime readiness wiring for :class:`HoudiniMcpServer`."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from dcc_mcp_core import ReadinessProbe

logger = logging.getLogger(__name__)

ENV_READINESS_TIMEOUT_SECS = "DCC_MCP_HOUDINI_READINESS_TIMEOUT_SECS"
READINESS_PROBE_REQUEST_ID = "dcc_mcp_houdini__readiness__dcc_ready_probe"

ProbeScheduler = Callable[[Any, Callable[[], None]], bool]


def resolve_readiness_timeout_secs(
    readiness_timeout_secs: Optional[int] = None,
) -> Optional[int]:
    """Resolve :data:`ENV_READINESS_TIMEOUT_SECS` into a positive integer."""
    if readiness_timeout_secs is not None:
        try:
            val = int(readiness_timeout_secs)
        except (TypeError, ValueError):
            return None
        return val if val > 0 else None

    raw = os.environ.get(ENV_READINESS_TIMEOUT_SECS)
    if not raw or not raw.strip():
        return None
    try:
        val = int(raw.strip())
    except ValueError:
        logger.warning(
            "Ignoring invalid %s=%r (expected positive integer seconds)",
            ENV_READINESS_TIMEOUT_SECS,
            raw,
        )
        return None
    return val if val > 0 else None


def _default_probe_scheduler(dispatcher: Any, on_done: Callable[[], None]) -> bool:
    """Schedule a dcc-ready probe on *dispatcher*."""
    submit_async = getattr(dispatcher, "submit_async_callable", None)
    if submit_async is None:
        on_done()
        return True

    def _on_complete(_result: Any) -> None:
        on_done()

    submit_async(
        request_id=READINESS_PROBE_REQUEST_ID,
        task=lambda: None,
        affinity="main",
        timeout_ms=5_000,
        on_complete=_on_complete,
    )
    return True


class ReadinessBinder:
    """Drive a :class:`dcc_mcp_core.ReadinessProbe` across a Houdini lifecycle."""

    def __init__(
        self,
        *,
        timeout_secs: Optional[int] = None,
        probe_scheduler: Optional[ProbeScheduler] = None,
    ) -> None:
        self.timeout_secs: Optional[int] = resolve_readiness_timeout_secs(timeout_secs)
        self.probe: ReadinessProbe = ReadinessProbe()
        self.probe_scheduler: ProbeScheduler = probe_scheduler or _default_probe_scheduler
        self.bound_server: Any = None
        self.bound_dispatcher: Any = None
        self.dcc_scheduled: bool = False
        self.published_to_server: bool = False

    def report(self) -> dict:
        """Return the current three-state readiness snapshot."""
        return self.probe.report()

    def is_ready(self) -> bool:
        """Return ``True`` when all three bits are green."""
        return self.probe.is_ready()

    def bind(self, server: Any) -> bool:
        """Wire the probe into *server*."""
        if self.bound_server is server:
            return self.dcc_scheduled
        self.bound_server = server

        server._server.set_readiness_probe(self.probe)
        self.published_to_server = True
        bridge = getattr(server, "_execution_bridge", None)
        host_dispatcher = bridge.resolve_host_dispatcher() if bridge is not None else None
        execution_ready = host_dispatcher is not None
        self.mark_dispatcher_ready(
            host_execution_bridge_ready=execution_ready,
            main_thread_executor_ready=execution_ready,
        )

        dispatcher = getattr(server, "_houdini_dispatcher", None)
        if dispatcher is None:
            self.bound_dispatcher = None
            self.mark_dcc_ready()
            self.dcc_scheduled = True
            return True

        self.bound_dispatcher = dispatcher
        self.dcc_scheduled = bool(self.probe_scheduler(dispatcher, self.mark_dcc_ready))
        return self.dcc_scheduled

    def mark_dispatcher_ready(
        self,
        value: bool = True,
        *,
        host_execution_bridge_ready: Optional[bool] = None,
        main_thread_executor_ready: Optional[bool] = None,
    ) -> None:
        """Flip the ``dispatcher`` bit."""
        self.probe.set_dispatcher_ready(value)
        if host_execution_bridge_ready is not None:
            self.probe.set_host_execution_bridge_ready(host_execution_bridge_ready)
        if main_thread_executor_ready is not None:
            self.probe.set_main_thread_executor_ready(main_thread_executor_ready)

    def mark_dcc_ready(self, value: bool = True) -> None:
        """Flip the ``dcc`` bit."""
        self.probe.set_dcc_ready(value)
        if value:
            logger.info("[houdini] readiness: dcc-ready — main thread is pumping")


def install_readiness(
    server: Any,
    *,
    timeout_secs: Optional[int] = None,
    probe_scheduler: Optional[ProbeScheduler] = None,
) -> ReadinessBinder:
    """One-shot helper used by :class:`HoudiniMcpServer.__init__`."""
    binder = ReadinessBinder(timeout_secs=timeout_secs, probe_scheduler=probe_scheduler)
    binder.bind(server)
    return binder


def wait_until_ready(server: Any, timeout: int = 30) -> bool:
    """Block until ``/v1/readyz`` returns 200 (or ``/health`` as fallback)."""
    import time
    import urllib.error
    import urllib.request

    port = getattr(server, "port", None)
    if port is None and hasattr(server, "_options"):
        port = getattr(server._options, "port", 8765)
    port = int(port or 8765)

    urls = (
        f"http://127.0.0.1:{port}/v1/readyz",
        f"http://127.0.0.1:{port}/health",
    )
    deadline = time.time() + timeout

    while time.time() < deadline:
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status == 200:
                        logger.info("Houdini MCP server ready on port %s (%s)", port, url)
                        return True
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
        time.sleep(0.5)

    logger.warning("Houdini MCP server not ready after %ss", timeout)
    return False
