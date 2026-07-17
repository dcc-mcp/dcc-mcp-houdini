"""Command-line entry point for dcc-mcp-houdini."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

from dcc_mcp_houdini import serve_headless


def main(argv: Optional[list[str]] = None) -> int:
    """Run the Houdini MCP server."""
    parser = argparse.ArgumentParser(description="Houdini MCP Server")
    parser.add_argument("--port", type=int, default=None, help="Instance port (default: operating-system assigned)")
    parser.add_argument("--gateway-port", type=int, default=None, help="Gateway port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:

        def _announce(server) -> None:
            print(f"Houdini MCP server started: {server.mcp_url}", flush=True)
            print("Press Ctrl+C to stop...", flush=True)

        serve_headless(port=args.port, gateway_port=args.gateway_port, on_started=_announce)
    except KeyboardInterrupt:
        print("\nShutting down...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
