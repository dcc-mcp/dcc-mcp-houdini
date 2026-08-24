"""Live Houdini E2E smoke test for dcc-mcp-houdini."""

from __future__ import annotations

import json
import queue
import textwrap
import threading
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
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


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
    assert result.get("isError") is not True, payload
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


def _call_tool(url, name, arguments=None):
    payload = _post(
        url,
        "tools/call",
        {"name": name, "arguments": arguments or {}},
    )
    assert "result" in payload, payload
    return _tool_payload(payload)


def _execute_json(url, execute_python, code):
    payload = _call_tool(
        url,
        execute_python,
        {"code": textwrap.dedent(code)},
    )
    context = payload.get("context") or {}
    result = context.get("result")
    assert result is not None, payload
    return json.loads(result)


def _serve_with_client_worker(serve_headless, client, join_timeout=5, **serve_kwargs):
    """Run exactly one HTTP client while the owner thread pumps HOM work."""
    stop_event = threading.Event()
    outcomes = queue.Queue(maxsize=1)
    workers = []

    def run_client(server):
        try:
            client(server)
        except BaseException as exc:  # noqa: BLE001 - rethrow on the owner thread
            outcomes.put((False, exc, exc.__traceback__))
        else:
            outcomes.put((True, None, None))
        finally:
            stop_event.set()

    def on_started(server):
        if workers:
            raise RuntimeError("serve_headless called on_started more than once")
        worker = threading.Thread(
            target=run_client,
            args=(server,),
            name="houdini-e2e-http-client",
            daemon=True,
        )
        workers.append(worker)
        worker.start()

    serve_headless(stop_event=stop_event, on_started=on_started, **serve_kwargs)
    if not workers:
        raise RuntimeError("serve_headless returned before starting the HTTP client")
    worker = workers[0]
    worker.join(timeout=join_timeout)
    if worker.is_alive():
        raise RuntimeError("Houdini E2E HTTP client did not stop")
    try:
        succeeded, error, traceback = outcomes.get_nowait()
    except queue.Empty as exc:
        raise RuntimeError("Houdini E2E HTTP client produced no outcome") from exc
    if not succeeded:
        raise error.with_traceback(traceback)


def _run_client(server):
    url = server.mcp_url
    initialized = _post(
        url,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "houdini-ci", "version": "1"},
        },
    )
    assert initialized["result"]["serverInfo"]["name"] == "dcc-mcp-houdini", initialized

    initial_names = _tool_names(_post(url, "tools/list"))
    load_skill = _find_tool(initial_names, "load_skill")
    for skill_name in ("houdini-scripting", "houdini-nodes", "houdini-kinefx"):
        loaded = _call_tool(url, load_skill, {"skill_name": skill_name})
        assert loaded.get("context", {}).get("loaded") is not False, loaded

    names = _tool_names(_post(url, "tools/list"))
    get_session_info = _find_tool(names, "get_session_info")
    execute_python = _find_tool(names, "execute_python")
    inspect_selection = _find_tool(names, "inspect_selection")
    create_node = _find_tool(names, "create_node")
    set_node_parms = _find_tool(names, "set_node_parms")
    create_rig = _find_tool(names, "create_rig")
    set_rig_pose = _find_tool(names, "set_rig_pose")
    delete_node = _find_tool(names, "delete_node")

    _call_tool(url, get_session_info)
    node_name = "dcc_mcp_ci_geo"
    node_path = "/obj/" + node_name
    mesh_name = "ci_mesh"
    mesh_path = node_path + "/" + mesh_name
    rig_path = node_path + "/ci_rig"

    _execute_json(
        url,
        execute_python,
        """
        import json
        existing = hou.node({node_path!r})
        if existing is not None:
            existing.destroy()
        result = json.dumps({{"absent": hou.node({node_path!r}) is None}})
        """.format(node_path=node_path),
    )

    _call_tool(
        url,
        create_node,
        {
            "parent_path": "/obj",
            "node_type": "geo",
            "node_name": node_name,
        },
    )
    _call_tool(
        url,
        create_node,
        {
            "parent_path": node_path,
            "node_type": "sphere",
            "node_name": mesh_name,
        },
    )
    _call_tool(
        url,
        set_node_parms,
        {"node_path": mesh_path, "parameters": {"type": 1}},
    )

    packed = _execute_json(
        url,
        execute_python,
        """
        import json
        mesh = hou.node({mesh_path!r})
        if mesh is None:
            raise RuntimeError("MCP-created sphere is missing")
        pack = mesh.parent().createNode("pack", "ci_pack")
        pack.setInput(0, mesh)
        pack.setDisplayFlag(True)
        pack.setCurrent(True, clear_all_selected=True)
        pack.cook(force=True)
        result = json.dumps({{
            "path": pack.path(),
            "point_count": pack.geometry().pointCount(),
            "packed_count": pack.geometry().countPrimType("PackedGeometry"),
        }})
        """.format(mesh_path=mesh_path),
    )
    assert packed["packed_count"] == 1, packed

    inspect_started = time.monotonic()
    inspected = _call_tool(url, inspect_selection)
    inspect_elapsed = time.monotonic() - inspect_started
    inspect_context = inspected["context"]
    assert inspect_context["selection"][0]["path"] == packed["path"], inspected
    assert inspect_context["display_node"]["path"] == packed["path"], inspected
    assert inspect_context["geometry"]["needs_cook"] is False, inspected
    assert inspect_context["geometry"]["point_count"] == packed["point_count"], inspected
    assert inspect_context["geometry"]["packed_primitive_count"] == 1, inspected
    assert "P" in inspect_context["geometry"]["key_attributes"]["point"], inspected
    assert inspect_elapsed <= 60.0, "inspect_selection exceeded 60s: {:.3f}s".format(inspect_elapsed)
    print(
        "inspect_selection elapsed_seconds={:.3f} point_count={} packed_count={}".format(
            inspect_elapsed,
            inspect_context["geometry"]["point_count"],
            inspect_context["geometry"]["packed_primitive_count"],
        )
    )

    _call_tool(
        url,
        create_rig,
        {
            "geo_path": node_path,
            "rig_name": "ci_rig",
            "joint_chain": [
                {"name": "root", "parent_index": -1, "translate": [0, -1, 0]},
                {"name": "spine", "parent_index": 0, "translate": [0, 1, 0]},
                {"name": "neck", "parent_index": 0, "translate": [1, 0, 0]},
            ],
            "auto_capture": True,
            "capture_mesh": mesh_name,
        },
    )
    rig_state = _execute_json(
        url,
        execute_python,
        """
        import json
        rig = hou.node({rig_path!r})
        capture = hou.node({capture_path!r})
        deform = hou.node({deform_path!r})
        if rig is None or capture is None or deform is None:
            raise RuntimeError("KineFX capture graph is incomplete")
        deform.cook(force=True)
        result = json.dumps({{
            "names": [point.attribValue("name") for point in rig.geometry().points()],
            "edges": sorted([list(point.number() for point in prim.points()) for prim in rig.geometry().prims()]),
            "capture": capture.geometry().findPointAttrib("boneCapture") is not None,
            "errors": list(deform.errors()),
            "rest": [list(point.position()) for point in deform.geometry().points()],
        }})
        """.format(
            rig_path=rig_path,
            capture_path=node_path + "/capture_ci_rig",
            deform_path=node_path + "/jointdeform_ci_rig",
        ),
    )
    assert rig_state["names"] == ["root", "spine", "neck"], rig_state
    assert rig_state["edges"] == [[0, 1], [0, 2]], rig_state
    assert rig_state["capture"] is True, rig_state
    assert rig_state["errors"] == [], rig_state

    _call_tool(
        url,
        set_rig_pose,
        {
            "rig_node": rig_path,
            "joint_name": "spine",
            "translate": [0.25, 1.0, 0.0],
            "rotate": [90.0, 0.0, 0.0],
            "scale": [1.0, 2.0, 1.0],
        },
    )
    posed_state = _execute_json(
        url,
        execute_python,
        """
        import json
        rig = hou.node({rig_path!r})
        deform = hou.node({deform_path!r})
        spine = rig.geometry().points()[1]
        expected = hou.Matrix3(hou.hmath.buildTransform({{
            "rotate": (90.0, 0.0, 0.0),
            "scale": (1.0, 2.0, 1.0),
        }})).asTuple()
        deform.cook(force=True)
        result = json.dumps({{
            "spine_x": spine.position()[0],
            "transform_delta": max(abs(actual - wanted) for actual, wanted in zip(
                spine.attribValue("transform"), expected
            )),
            "errors": list(deform.errors()),
            "positions": [list(point.position()) for point in deform.geometry().points()],
        }})
        """.format(
            rig_path=rig_path,
            deform_path=node_path + "/jointdeform_ci_rig",
        ),
    )
    assert abs(posed_state["spine_x"] - 0.25) < 1e-6, posed_state
    assert posed_state["transform_delta"] < 1e-6, posed_state
    assert posed_state["errors"] == [], posed_state
    assert any(before != after for before, after in zip(rig_state["rest"], posed_state["positions"])), posed_state

    _call_tool(url, delete_node, {"node_path": node_path})
    deleted_state = _execute_json(
        url,
        execute_python,
        """
        import json
        result = json.dumps({{"absent": hou.node({node_path!r}) is None}})
        """.format(node_path=node_path),
    )
    assert deleted_state["absent"] is True, deleted_state
    print("Houdini MCP E2E passed:", url)


def main() -> None:
    print("Houdini:", hou.applicationVersionString())
    _serve_with_client_worker(
        dcc_mcp_houdini.serve_headless,
        _run_client,
        join_timeout=30,
        port=0,
        gateway_port=0,
        register_builtins=True,
    )


if __name__ == "__main__":
    main()
