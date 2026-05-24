"""Headless Houdini bootstrap for the MCP server.

Run with:
    hython examples/houdini_bootstrap.py
"""

from __future__ import annotations

from dcc_mcp_core.host import BlockingDispatcher

from dcc_mcp_houdini.host import HoudiniCallableDispatcher, HoudiniHost
from dcc_mcp_houdini.server import HoudiniMcpServer


def main(port: int = 18765) -> None:
    """Start the MCP server and block while the headless host pumps jobs."""
    blocking = BlockingDispatcher()
    dispatcher = HoudiniCallableDispatcher(blocking)
    server = HoudiniMcpServer(port=port, dispatcher=dispatcher)
    server.register_builtin_actions()
    server.start()
    server.discover_skills()
    print(f"MCP_URL={server.mcp_url}", flush=True)
    try:
        HoudiniHost(blocking).run_headless()
    finally:
        server.stop()


if __name__ == "__main__":
    main()
