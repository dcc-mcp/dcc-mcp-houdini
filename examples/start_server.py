"""Example: start dcc-mcp-houdini inside Houdini.

Run in Houdini's Python Source Editor. For headless Hython use:

    hython examples/houdini_bootstrap.py
"""

from __future__ import annotations

import dcc_mcp_houdini

print("Starting dcc-mcp-houdini server...")
server = dcc_mcp_houdini.start_server()
print(f"MCP endpoint: {server.mcp_url}")
print(f"Loaded skills: {server.loaded_skill_count()}")
