"""Houdini thread-affinity dispatchers."""

from __future__ import annotations

from dcc_mcp_houdini.dispatcher.standalone import HoudiniStandaloneDispatcher
from dcc_mcp_houdini.host import HoudiniCallableDispatcher, HoudiniHost

__all__ = [
    "HoudiniCallableDispatcher",
    "HoudiniHost",
    "HoudiniStandaloneDispatcher",
    "create_execution_stack",
]


def create_execution_stack():
    """Create the dispatcher + optional host adapter for the current environment.

    Returns:
        ``(dispatcher, host)`` where *host* is a started :class:`HoudiniHost`
        in interactive mode, or ``None`` in headless ``hython``.
    """
    try:
        import hou  # noqa: PLC0415

        if hou.isUIAvailable():
            from dcc_mcp_core.host import BlockingDispatcher

            blocking = BlockingDispatcher()
            dispatcher = HoudiniCallableDispatcher(blocking)
            host = HoudiniHost(blocking)
            host.start()
            return dispatcher, host
    except ImportError:
        pass

    return HoudiniStandaloneDispatcher(), None
