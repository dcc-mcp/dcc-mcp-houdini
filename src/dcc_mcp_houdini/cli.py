"""Command-line entry point for dcc-mcp-houdini."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional, Sequence

from dcc_mcp_houdini import serve_headless

_LIFECYCLE_COMMANDS = frozenset(("install", "status", "verify", "uninstall", "upgrade"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run one lifecycle verb or the backward-compatible Houdini MCP server."""
    raw = list(argv) if argv is not None else sys.argv[1:]
    if raw and raw[0] in _LIFECYCLE_COMMANDS:
        from dcc_mcp_houdini.install_cli import main as install_main  # noqa: PLC0415

        return install_main(raw)

    parser = argparse.ArgumentParser(description="Houdini MCP Server")
    parser.add_argument("--port", type=int, default=None, help="Instance port (default: operating-system assigned)")
    parser.add_argument("--gateway-port", type=int, default=None, help="Gateway port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(raw)

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
