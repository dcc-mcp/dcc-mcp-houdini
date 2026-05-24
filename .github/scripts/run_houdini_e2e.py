"""Live Houdini E2E smoke test for dcc-mcp-houdini."""

from __future__ import annotations

import json
import time
import urllib.request

import hou

import dcc_mcp_houdini


def _post(url, method, params=None):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 100000,
            "method": method,
            "params": params or {},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _tool_names(payload):
    result = payload.get("result") or {}
    return [tool.get("name") for tool in result.get("tools", []) if tool.get("name")]


def _find_tool(names, suffix):
    for name in names:
        if name == suffix or name.endswith("__" + suffix):
            return name
    raise AssertionError("Tool ending with {!r} not found in {}".format(suffix, names))


def main() -> None:
    print("Houdini:", hou.applicationVersionString())
    server = dcc_mcp_houdini.start_server(port=0, register_builtins=True, wait_ready=True, readiness_timeout_secs=20)
    try:
        url = server.mcp_url
        init = _post(
            url,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "houdini-ci", "version": "1"},
            },
        )
        assert init["result"]["serverInfo"]["name"] == "dcc-mcp-houdini", init

        server.load_skill("houdini-nodes")
        tools = _post(url, "tools/list")
        names = _tool_names(tools)
        get_session_info = _find_tool(names, "get_session_info")
        create_node = _find_tool(names, "create_node")
        delete_node = _find_tool(names, "delete_node")

        session = _post(url, "tools/call", {"name": get_session_info, "arguments": {}})
        assert "result" in session, session

        node_name = "dcc_mcp_ci_geo"
        existing = hou.node("/obj/" + node_name)
        if existing is not None:
            existing.destroy()
        created = _post(
            url,
            "tools/call",
            {
                "name": create_node,
                "arguments": {
                    "parent_path": "/obj",
                    "node_type": "geo",
                    "node_name": node_name,
                },
            },
        )
        assert "result" in created, created
        assert hou.node("/obj/" + node_name) is not None

        deleted = _post(url, "tools/call", {"name": delete_node, "arguments": {"node_path": "/obj/" + node_name}})
        assert "result" in deleted, deleted
        assert hou.node("/obj/" + node_name) is None
        print("Houdini MCP E2E passed:", url)
    finally:
        dcc_mcp_houdini.stop_server()


if __name__ == "__main__":
    main()
