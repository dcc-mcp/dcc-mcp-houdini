"""Houdini thread-affinity dispatchers."""

from __future__ import annotations

from dcc_mcp_houdini.dispatcher.standalone import HoudiniStandaloneDispatcher
from dcc_mcp_houdini.host import HoudiniCallableDispatcher, HoudiniHost, HoudiniUiDispatcher, HoudiniUiPump

__all__ = [
    "HoudiniCallableDispatcher",
    "HoudiniHost",
    "HoudiniStandaloneDispatcher",
    "HoudiniUiDispatcher",
    "HoudiniUiPump",
    "create_execution_stack",
]


def create_execution_stack():
    """Create the dispatcher + optional host adapter for the current environment.

    Returns:
        ``(dispatcher, host)`` where interactive Houdini receives a started
        :class:`HoudiniUiPump`, while headless ``hython`` receives an unstarted
        :class:`HoudiniHost` that its foreground entry point must pump.
    """
    try:
        import hou  # noqa: PLC0415

        ui_available = bool(hou.isUIAvailable())
    except ImportError:
        ui_available = False

    if not ui_available:
        from dcc_mcp_core.host import BlockingDispatcher

        blocking = BlockingDispatcher()
        return HoudiniCallableDispatcher(blocking), HoudiniHost(blocking)

    dispatcher = HoudiniUiDispatcher()
    host = HoudiniUiPump(dispatcher)
    host.start()
    return dispatcher, host
