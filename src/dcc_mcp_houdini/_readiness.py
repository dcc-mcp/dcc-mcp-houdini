"""Readiness helpers for HoudiniMcpServer."""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def wait_until_ready(server: Any, timeout: int = 30) -> bool:
    """Block until the server is ready (or timeout)."""
    import requests

    url = f"http://127.0.0.1:{server.port}/health"
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                logger.info("Houdini MCP server ready on port %s", server.port)
                return True
        except Exception:
            pass
        time.sleep(0.5)

    logger.warning("Houdini MCP server not ready after %ss", timeout)
    return False
