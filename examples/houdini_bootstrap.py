"""Headless Houdini bootstrap for the MCP server.

Run with:
    hython examples/houdini_bootstrap.py
"""

from __future__ import annotations

from typing import Optional

from dcc_mcp_houdini.server import serve_headless


def main(port: Optional[int] = None) -> None:
    """Start the MCP server and block while the headless host pumps jobs."""
    serve_headless(
        port=port,
        on_started=lambda server: print(f"MCP_URL={server.mcp_url}", flush=True),
    )


if __name__ == "__main__":
    main()
