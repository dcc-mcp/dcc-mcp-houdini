"""Basic tests for dcc-mcp-houdini."""

from __future__ import annotations

import pytest


def test_import() -> None:
    """Test that dcc_mcp_houdini can be imported."""
    import dcc_mcp_houdini

    assert hasattr(dcc_mcp_houdini, "__version__")
    assert hasattr(dcc_mcp_houdini, "HoudiniMcpServer")


def test_version() -> None:
    """Test version is a string."""
    from dcc_mcp_houdini import __version__

    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_server_options() -> None:
    """Test HoudiniServerOptions dataclass."""
    from dcc_mcp_houdini.server import HoudiniServerOptions

    opts = HoudiniServerOptions()
    assert opts.port == 8765
    assert opts.server_name == "dcc-mcp-houdini"
    assert opts.gateway_port is None


def test_server_options_to_core() -> None:
    """Test HoudiniServerOptions.to_core_options()."""
    from dcc_mcp_houdini.server import HoudiniServerOptions

    opts = HoudiniServerOptions(port=9000, dcc_version="20.5")
    core_opts = opts.to_core_options()

    assert core_opts is not None
    assert core_opts.port == 9000


def test_file_registry_registration_survives_disabled_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disabling failover must not disable FileRegistry self-registration."""
    monkeypatch.setenv("DCC_MCP_GATEWAY_PORT", "19876")

    from dcc_mcp_houdini.server import HoudiniMcpServer

    server = HoudiniMcpServer(port=0, enable_gateway_failover=False, job_storage_path="")
    try:
        assert server._enable_gateway_failover is False
        assert server._config.gateway_port == 19876
    finally:
        server.stop()


def test_explicit_zero_gateway_port_disables_registration() -> None:
    """gateway_port=0 remains the explicit opt-out for FileRegistry registration."""
    from dcc_mcp_houdini.server import HoudiniMcpServer

    server = HoudiniMcpServer(port=0, gateway_port=0, enable_gateway_failover=False, job_storage_path="")
    try:
        assert server._config.gateway_port == 0
    finally:
        server.stop()


@pytest.mark.skip(reason="Requires Houdini environment")
def test_server_creation() -> None:
    """Test HoudiniMcpServer creation (requires Houdini)."""
    from dcc_mcp_houdini.server import HoudiniMcpServer

    server = HoudiniMcpServer(port=18765)
    assert server is not None
    server.shutdown()
