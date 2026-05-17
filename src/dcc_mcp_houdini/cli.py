"""Command-line entry point for dcc-mcp-houdini."""

from __future__ import annotations

import argparse
import logging
import sys

from dcc_mcp_houdini import HoudiniMcpServer


def main(argv: Optional[list[str]] = None) -> int:
    """Run the Houdini MCP server."""
    parser = argparse.ArgumentParser(description="Houdini MCP Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--gateway-port", type=int, default=None, help="Gateway port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server = HoudiniMcpServer(port=args.port, gateway_port=args.gateway_port)
    handle = server.start()

    print(f"Houdini MCP server started: {handle.mcp_url()}")
    print("Press Ctrl+C to stop...")

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
