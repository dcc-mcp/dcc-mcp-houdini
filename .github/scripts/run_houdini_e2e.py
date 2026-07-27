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


def _tool_payload(payload):
    result = payload.get("result") or {}
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for item in result.get("content") or []:
        if item.get("type") != "text":
            continue
        try:
            decoded = json.loads(item.get("text") or "")
        except (TypeError, ValueError):
            continue
        if isinstance(decoded, dict):
            return decoded
    raise AssertionError("Structured tool payload not found in {!r}".format(payload))


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
        server.load_skill("houdini-kinefx")
        tools = _post(url, "tools/list")
        names = _tool_names(tools)
        get_session_info = _find_tool(names, "get_session_info")
        inspect_selection = _find_tool(names, "inspect_selection")
        create_node = _find_tool(names, "create_node")
        set_node_parms = _find_tool(names, "set_node_parms")
        create_rig = _find_tool(names, "create_rig")
        set_rig_pose = _find_tool(names, "set_rig_pose")
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

        mesh_name = "ci_mesh"
        mesh_created = _post(
            url,
            "tools/call",
            {
                "name": create_node,
                "arguments": {
                    "parent_path": "/obj/" + node_name,
                    "node_type": "sphere",
                    "node_name": mesh_name,
                },
            },
        )
        assert "result" in mesh_created, mesh_created
        mesh_path = "/obj/{}/{}".format(node_name, mesh_name)
        assert hou.node(mesh_path) is not None
        mesh_configured = _post(
            url,
            "tools/call",
            {
                "name": set_node_parms,
                "arguments": {
                    "node_path": mesh_path,
                    "parameters": {"type": 1},
                },
            },
        )
        assert "result" in mesh_configured, mesh_configured
        mesh = hou.node(mesh_path)
        pack = mesh.parent().createNode("pack", "ci_pack")
        pack.setInput(0, mesh)
        pack.setDisplayFlag(True)
        pack.setCurrent(True, clear_all_selected=True)
        pack.cook(force=True)
        assert pack.geometry().countPrimType("PackedGeometry") == 1
        inspect_started = time.monotonic()
        inspected = _post(url, "tools/call", {"name": inspect_selection, "arguments": {}})
        inspect_elapsed = time.monotonic() - inspect_started
        inspect_payload = _tool_payload(inspected)
        inspect_context = inspect_payload["context"]
        assert inspect_context["selection"][0]["path"] == pack.path(), inspect_payload
        assert inspect_context["display_node"]["path"] == pack.path(), inspect_payload
        assert inspect_context["geometry"]["needs_cook"] is False, inspect_payload
        assert inspect_context["geometry"]["point_count"] == pack.geometry().pointCount(), inspect_payload
        assert inspect_context["geometry"]["packed_primitive_count"] == 1, inspect_payload
        assert "P" in inspect_context["geometry"]["key_attributes"]["point"], inspect_payload
        assert inspect_elapsed <= 60.0, "inspect_selection exceeded 60s: {:.3f}s".format(inspect_elapsed)
        print(
            "inspect_selection elapsed_seconds={:.3f} point_count={} packed_count={}".format(
                inspect_elapsed,
                inspect_context["geometry"]["point_count"],
                inspect_context["geometry"]["packed_primitive_count"],
            )
        )

        rigged = _post(
            url,
            "tools/call",
            {
                "name": create_rig,
                "arguments": {
                    "geo_path": "/obj/" + node_name,
                    "rig_name": "ci_rig",
                    "joint_chain": [
                        {"name": "root", "parent_index": -1, "translate": [0, -1, 0]},
                        {"name": "spine", "parent_index": 0, "translate": [0, 1, 0]},
                        {"name": "neck", "parent_index": 0, "translate": [1, 0, 0]},
                    ],
                    "auto_capture": True,
                    "capture_mesh": mesh_name,
                },
            },
        )
        assert "result" in rigged, rigged
        rig = hou.node("/obj/{}/ci_rig".format(node_name))
        assert rig is not None
        assert len(rig.geometry().points()) == 3
        assert len(rig.geometry().prims()) == 2
        assert [point.attribValue("name") for point in rig.geometry().points()] == ["root", "spine", "neck"]
        assert sorted(tuple(point.number() for point in prim.points()) for prim in rig.geometry().prims()) == [
            (0, 1),
            (0, 2),
        ]
        capture = hou.node("/obj/{}/capture_ci_rig".format(node_name))
        joint_deform = hou.node("/obj/{}/jointdeform_ci_rig".format(node_name))
        assert capture is not None and capture.geometry().findPointAttrib("boneCapture") is not None
        assert joint_deform is not None and not joint_deform.errors()
        rest_positions = [tuple(point.position()) for point in joint_deform.geometry().points()]

        posed = _post(
            url,
            "tools/call",
            {
                "name": set_rig_pose,
                "arguments": {
                    "rig_node": rig.path(),
                    "joint_name": "spine",
                    "translate": [0.25, 1.0, 0.0],
                    "rotate": [90.0, 0.0, 0.0],
                    "scale": [1.0, 2.0, 1.0],
                },
            },
        )
        assert "result" in posed, posed
        spine = rig.geometry().points()[1]
        assert abs(spine.position()[0] - 0.25) < 1e-6
        expected_transform = hou.Matrix3(
            hou.hmath.buildTransform({"rotate": (90.0, 0.0, 0.0), "scale": (1.0, 2.0, 1.0)})
        ).asTuple()
        assert (
            max(abs(actual - expected) for actual, expected in zip(spine.attribValue("transform"), expected_transform))
            < 1e-6
        )
        joint_deform.cook(force=True)
        assert not joint_deform.errors()
        assert len(joint_deform.geometry().points()) > 0
        posed_positions = [tuple(point.position()) for point in joint_deform.geometry().points()]
        assert any(before != after for before, after in zip(rest_positions, posed_positions))

        deleted = _post(url, "tools/call", {"name": delete_node, "arguments": {"node_path": "/obj/" + node_name}})
        assert "result" in deleted, deleted
        assert hou.node("/obj/" + node_name) is None
        print("Houdini MCP E2E passed:", url)
    finally:
        dcc_mcp_houdini.stop_server()


if __name__ == "__main__":
    main()
