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


@pytest.mark.skip(reason="Requires Houdini environment")
def test_server_creation() -> None:
    """Test HoudiniMcpServer creation (requires Houdini)."""
    from dcc_mcp_houdini.server import HoudiniMcpServer

    server = HoudiniMcpServer(port=18765)
    assert server is not None
    server.shutdown()
