"""Example: start dcc-mcp-houdini inside Houdini.

Run in Houdini's Python Source Editor, or:

    hython examples/start_server.py
"""

from __future__ import annotations

import dcc_mcp_houdini

print("Starting dcc-mcp-houdini server...")
server = dcc_mcp_houdini.start_server()

print(f"MCP endpoint: {server.mcp_url}")
print(f"Loaded skills: {server.loaded_skill_count()}")

try:
    import time

    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping server...")
    dcc_mcp_houdini.stop_server()
    print("Done.")
