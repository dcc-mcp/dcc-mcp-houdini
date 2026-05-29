"""Server-level wiring tests for the core integrations.

These build a real :class:`HoudiniMcpServer` (no live Houdini, no started HTTP
listener) and confirm :meth:`register_builtin_actions` attaches the optional
core integrations and that they degrade gracefully under env opt-outs.
"""

from __future__ import annotations

import pytest

from dcc_mcp_houdini import HoudiniMcpServer
from dcc_mcp_houdini._env import ENV_PROJECT_TOOLS, ENV_RESOURCES


def _make_server() -> HoudiniMcpServer:
    return HoudiniMcpServer(port=0, gateway_port=0, enable_gateway_failover=False, job_storage_path="")


def test_register_builtin_actions_wires_resources_and_project_tools() -> None:
    server = _make_server()
    try:
        server.register_builtin_actions(include_bundled=True)
        assert server._resources is not None
        assert server._resources.handle is not None
        assert server._project_tools is not None
    finally:
        try:
            server.stop()
        except Exception:  # noqa: BLE001
            pass


def test_build_capability_manifest_returns_payload() -> None:
    server = _make_server()
    try:
        server.register_builtin_actions(include_bundled=True)
        payload = server.build_capability_manifest()
        assert payload["dcc_type"] == "houdini"
        assert payload["schema_version"] == "1"
        assert set(payload["totals"]) >= {"actions", "loaded_actions", "unloaded_actions"}
        assert isinstance(payload["capabilities"], list)
        assert payload["capabilities"], "expected at least one capability record"
        for record in payload["capabilities"]:
            assert "backend_tool" in record
            assert "tool_slug" in record
            assert "loaded" in record
    finally:
        try:
            server.stop()
        except Exception:  # noqa: BLE001
            pass


def test_resources_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_RESOURCES, "0")
    server = _make_server()
    try:
        server.register_builtin_actions(include_bundled=True)
        assert server._resources is None
    finally:
        try:
            server.stop()
        except Exception:  # noqa: BLE001
            pass


def test_project_tools_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_PROJECT_TOOLS, "0")
    server = _make_server()
    try:
        server.register_builtin_actions(include_bundled=True)
        assert server._project_tools is None
    finally:
        try:
            server.stop()
        except Exception:  # noqa: BLE001
            pass


def test_capability_manifest_loaded_only_filters() -> None:
    server = _make_server()
    try:
        server.register_builtin_actions(include_bundled=True)
        full = server.build_capability_manifest()
        loaded = server.build_capability_manifest(loaded_only=True)
        assert loaded["totals"]["actions"] <= full["totals"]["actions"]
        assert all(c.get("loaded", False) for c in loaded["capabilities"])
    finally:
        try:
            server.stop()
        except Exception:  # noqa: BLE001
            pass
