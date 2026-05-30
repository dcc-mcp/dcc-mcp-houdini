"""Tests for Houdini server helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_minimal_mode_config() -> None:
    from dcc_mcp_houdini._skill_loader import MINIMAL_SKILLS, build_minimal_mode_config

    cfg = build_minimal_mode_config()
    assert tuple(cfg.skills) == MINIMAL_SKILLS


def test_resolve_minimal_mode_default() -> None:
    from dcc_mcp_houdini._env import resolve_minimal_mode_enabled

    with patch.dict("os.environ", {}, clear=True):
        assert resolve_minimal_mode_enabled() is True


def test_houdini_server_options_port() -> None:
    from dcc_mcp_houdini.server import HoudiniServerOptions

    opts = HoudiniServerOptions(port=9001)
    core = opts.to_core_options()
    assert core.port == 9001


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

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResp())

    server = MagicMock()
    server.port = 8765
    assert wait_until_ready(server, timeout=1) is True


def test_api_helpers() -> None:
    from dcc_mcp_houdini.api import houdini_error, houdini_success

    ok = houdini_success("done", count=1)
    assert ok["status"] == "success"
    err = houdini_error("fail")
    assert err["status"] == "error"
