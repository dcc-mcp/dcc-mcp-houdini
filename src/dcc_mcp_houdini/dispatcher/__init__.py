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
        :class:`HoudiniUiPump`, while headless ``hython`` uses inline dispatch.
    """
    try:
        import hou  # noqa: PLC0415

        ui_available = bool(hou.isUIAvailable())
    except ImportError:
        ui_available = False

    if not ui_available:
        return HoudiniStandaloneDispatcher(), None

    dispatcher = HoudiniUiDispatcher()
    host = HoudiniUiPump(dispatcher)
    host.start()
    return dispatcher, host
