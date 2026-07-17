"""Headless Hython server lifecycle regressions.

Metadata-only checks cannot prove that HOM work reaches Hython's owning
thread.  These tests therefore cross the real MCP HTTP boundary and require a
main-affinity tool to report the same thread that entered the foreground pump.
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _post_mcp(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_headless_stack_is_an_unstarted_foreground_pump() -> None:
    from dcc_mcp_houdini.dispatcher import create_execution_stack
    from dcc_mcp_houdini.host import HoudiniCallableDispatcher, HoudiniHost

    hou = SimpleNamespace(isUIAvailable=lambda: False)
    with patch.dict(sys.modules, {"hou": hou}):
        dispatcher, host = create_execution_stack()

    assert isinstance(dispatcher, HoudiniCallableDispatcher)
    assert isinstance(host, HoudiniHost)
    assert host.is_running is False


def test_start_server_rejects_headless_mode_before_server_construction(monkeypatch, tmp_path) -> None:
    import dcc_mcp_houdini.server as server_module

    hou = SimpleNamespace(isUIAvailable=lambda: False)
    constructed = []

    class UnexpectedServer:
        def __init__(self, *args, **kwargs) -> None:
            constructed.append((args, kwargs))

    monkeypatch.setattr(server_module, "HoudiniMcpServer", UnexpectedServer)
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    with patch.dict(sys.modules, {"hou": hou}):
        with pytest.raises(RuntimeError, match="serve_headless"):
            server_module.start_server(wait_ready=False)

    assert constructed == []


def test_serve_headless_runs_real_main_affinity_on_owning_thread(monkeypatch, tmp_path) -> None:
    from dcc_mcp_houdini.server import serve_headless

    monkeypatch.setenv("MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_GATEWAY_PORT", "0")
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("DCC_MCP_MINIMAL", "1")

    owner_thread = threading.get_ident()
    stop_event = threading.Event()
    client_errors = []
    client_threads = []
    observations = {}
    hou = SimpleNamespace(isUIAvailable=lambda: False)

    def on_started(server) -> None:
        observations["url"] = server.mcp_url

        def client() -> None:
            try:
                listed = _post_mcp(
                    server.mcp_url,
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
                observations["listed"] = {tool["name"] for tool in listed["result"]["tools"]}
                observations["loaded"] = _post_mcp(
                    server.mcp_url,
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "load_skill",
                            "arguments": {"skill_name": "houdini-scripting"},
                        },
                    },
                )
                called = _post_mcp(
                    server.mcp_url,
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "execute_python",
                            "arguments": {
                                "code": "import threading\nresult = threading.get_ident()",
                            },
                        },
                    },
                )
                observations["called"] = called
            except BaseException as exc:  # noqa: BLE001 - forward client-thread failures
                client_errors.append(exc)
            finally:
                stop_event.set()

        thread = threading.Thread(target=client, name="headless-mcp-client", daemon=True)
        client_threads.append(thread)
        thread.start()

    with patch.dict(sys.modules, {"hou": hou}):
        serve_headless(
            gateway_port=0,
            registry_dir=str(tmp_path / "registry"),
            stop_event=stop_event,
            on_started=on_started,
        )

    client_threads[0].join(timeout=1)
    assert client_errors == []
    assert client_threads[0].is_alive() is False
    assert observations["listed"]
    assert observations["loaded"]["result"]["isError"] is False
    called = observations["called"]
    assert called["result"]["isError"] is False
    assert called["result"]["structuredContent"]["context"]["result"] == str(owner_thread)

    from dcc_mcp_houdini.server import get_server

    assert get_server() is None


def test_headless_dispatch_wait_times_out_and_shutdown_cancels_pending_work() -> None:
    from dcc_mcp_core.host import DispatchError

    from dcc_mcp_houdini.host import HoudiniCallableDispatcher, HoudiniHost

    dispatcher = HoudiniCallableDispatcher()
    host = HoudiniHost(dispatcher.host_dispatcher)
    executed = []

    with pytest.raises(DispatchError):
        dispatcher.dispatch_callable(
            lambda: executed.append(True),
            timeout_hint_secs=0.01,
        )

    assert dispatcher.host_dispatcher.has_pending() is True
    host.stop()
    assert dispatcher.is_shutdown() is True
    assert executed == []
