"""Tests for Houdini server helpers."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


def test_minimal_mode_config() -> None:
    from dcc_mcp_houdini._skill_loader import MINIMAL_SKILLS, build_minimal_mode_config

    cfg = build_minimal_mode_config()
    assert tuple(cfg.skills) == MINIMAL_SKILLS
    assert cfg.deactivate_groups == {}


def test_configure_core_logging_defaults_to_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    from dcc_mcp_houdini._env import configure_core_logging

    monkeypatch.delenv("MCP_LOG_LEVEL", raising=False)
    configure_core_logging()

    assert "WARN" == os.environ["MCP_LOG_LEVEL"]
    assert "WARN" == os.environ["DCC_MCP_LOG_LEVEL"]


def test_configure_core_logging_preserves_user_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    from dcc_mcp_houdini._env import configure_core_logging

    monkeypatch.delenv("MCP_LOG_LEVEL", raising=False)
    monkeypatch.setenv("DCC_MCP_LOG_LEVEL", "DEBUG")
    configure_core_logging()

    assert "DEBUG" == os.environ["DCC_MCP_LOG_LEVEL"]
    assert "DEBUG" == os.environ["MCP_LOG_LEVEL"]


def test_resolve_minimal_mode_default() -> None:
    from dcc_mcp_houdini._env import resolve_minimal_mode_enabled

    with patch.dict("os.environ", {}, clear=True):
        assert resolve_minimal_mode_enabled() is True


def test_houdini_server_options_port() -> None:
    from dcc_mcp_houdini.host import HoudiniCallableDispatcher, HoudiniInlineCallableDispatcher
    from dcc_mcp_houdini.server import HoudiniServerOptions

    dispatcher = HoudiniCallableDispatcher()
    opts = HoudiniServerOptions(port=9001, dispatcher=dispatcher)
    core = opts.to_core_options()
    bridge = core.execution.mode.bridge
    assert core.port == 9001
    assert isinstance(bridge.dispatcher, HoudiniInlineCallableDispatcher)
    assert bridge.host_dispatcher is dispatcher.host_dispatcher


def test_houdini_ui_dispatcher_bridge_attaches_http_queue() -> None:
    from dcc_mcp_houdini.host import HoudiniUiDispatcher
    from dcc_mcp_houdini.server import HoudiniServerOptions

    dispatcher = HoudiniUiDispatcher()
    bridge = HoudiniServerOptions(dispatcher=dispatcher).to_core_options().execution.mode.bridge
    host_dispatcher = bridge.resolve_host_dispatcher()

    assert bridge.dispatcher is dispatcher
    assert host_dispatcher is not None
    handle = host_dispatcher.post(lambda: "http-main")
    assert dispatcher.pending_count() == 1
    assert dispatcher.drain_queue(8) == (1, 0)
    assert handle.wait(0) == "http-main"


def test_create_execution_stack_without_hou() -> None:
    from dcc_mcp_houdini.dispatcher import create_execution_stack
    from dcc_mcp_houdini.dispatcher.standalone import HoudiniStandaloneDispatcher

    dispatcher, host = create_execution_stack()
    assert isinstance(dispatcher, HoudiniStandaloneDispatcher)
    assert host is None


def test_wait_until_ready_uses_urllib(monkeypatch: pytest.MonkeyPatch) -> None:
    from dcc_mcp_houdini._readiness import wait_until_ready

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    requested_urls = []

    def fake_urlopen(url, **kwargs):
        requested_urls.append(url)
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    server = MagicMock()
    server.mcp_url = "http://127.0.0.1:54321/mcp"
    assert wait_until_ready(server, timeout=1) is True
    assert requested_urls == ["http://127.0.0.1:54321/v1/readyz"]


def test_api_helpers() -> None:
    from dcc_mcp_houdini.api import houdini_error, houdini_success

    ok = houdini_success("done", count=1)
    assert ok["status"] == "success"
    err = houdini_error("fail")
    assert err["status"] == "error"
