"""Auto-start the MCP server when Houdini launches.

Install (pick one):

* Windows user scripts:
  ``%USERPROFILE%\\Documents\\houdini20.5\\scripts\\123.py``
* Or set ``HOUDINI_PATH`` / ``HS/site`` to a folder containing this file as ``123.py``

Set ``DCC_MCP_HOUDINI_AUTOSTART=0`` to disable.
"""

from __future__ import annotations

import os


def _autostart_enabled() -> bool:
    raw = os.environ.get("DCC_MCP_HOUDINI_AUTOSTART", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


if _autostart_enabled():
    try:
        import dcc_mcp_houdini

        server = dcc_mcp_houdini.start_server()
        print(f"[dcc-mcp-houdini] auto-started: {server.mcp_url}")
    except Exception as exc:  # noqa: BLE001
        print(f"[dcc-mcp-houdini] autostart failed: {exc}")
