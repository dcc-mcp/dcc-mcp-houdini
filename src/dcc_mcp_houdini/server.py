"""Houdini MCP server — embeds a Streamable HTTP MCP server inside Houdini."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from dcc_mcp_core import DccServerOptions
from dcc_mcp_core.server_base import DccServerBase

from dcc_mcp_houdini.__version__ import __version__

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

SERVER_NAME = "dcc-mcp-houdini"
SERVER_VERSION = __version__
DEFAULT_PORT = 8765

# Built-in skills directory shipped with this package
_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Environment variable for extra skill paths (colon/semicolon separated)
_ENV_EXTRA_SKILL_PATHS = "DCC_MCP_HOUDINI_SKILL_PATHS"
_ENV_GENERIC_SKILL_PATHS = "DCC_MCP_SKILL_PATHS"

_DCC_NAME = "houdini"


# ── options ──────────────────────────────────────────────────────────────────

@dataclass
class HoudiniServerOptions:
    """Adapter-local options collapsed for the dcc-mcp-core 0.17+ server contract."""

    port: int = DEFAULT_PORT
    extra_skill_paths: Optional[List[str]] = None
    server_name: str = SERVER_NAME
    server_version: str = SERVER_VERSION
    # Gateway options
    gateway_port: Optional[int] = None
    registry_dir: Optional[str] = None
    dcc_version: Optional[str] = None
    scene: Optional[str] = None
    enable_gateway_failover: Optional[bool] = None
    # Observability options
    metrics_enabled: Optional[bool] = None
    job_storage_path: Optional[str] = None
    enable_workflows: Optional[bool] = None
    # Diagnostics options (new in 0.17+)
    dcc_pid: Optional[int] = None
    dcc_window_title: Optional[str] = None
    dcc_window_handle: Optional[int] = None
    snapshot_provider: Optional[Any] = None
    # Execution options (new in 0.17+)
    dispatcher: Optional[Any] = None  # BaseDccCallableDispatcher
    execution_bridge: Optional[Any] = None  # HostExecutionBridge

    def to_core_options(self) -> DccServerOptions:
        """Convert to core DccServerOptions using from_env()."""
        from dcc_mcp_houdini import _env

        return DccServerOptions.from_env(
            dcc_name=_DCC_NAME,
            builtin_skills_dir=_BUILTIN_SKILLS_DIR,
            port=self.port,
            server_name=self.server_name,
            server_version=self.server_version,
            # Gateway kwargs
            gateway_port=self.gateway_port,
            registry_dir=self.registry_dir,
            dcc_version=self.dcc_version,
            scene=self.scene,
            enable_gateway_failover=_env.resolve_enable_gateway_failover(
                self.enable_gateway_failover
            ),
            # Observability kwargs
            enable_file_logging=True,  # default
            enable_job_persistence=_env.resolve_job_storage(self.job_storage_path) is not None,
            enable_telemetry=True,  # default
            # Diagnostics kwargs (new in 0.17+)
            dcc_pid=self.dcc_pid,
            dcc_window_title=self.dcc_window_title,
            dcc_window_handle=self.dcc_window_handle,
            snapshot_provider=self.snapshot_provider,
            # Execution kwargs (new in 0.17+)
            dispatcher=self.dispatcher,
            execution_bridge=self.execution_bridge,
        )


# ── server class ─────────────────────────────────────────────────────────────

class HoudiniMcpServer(DccServerBase):
    """MCP server embedded inside Houdini.

    Thin subclass of :class:`~dcc_mcp_core.server_base.DccServerBase`.
    All skill management, hot-reload, and gateway election logic is
    inherited.  This class adds only:

    - Houdini built-in skills directory (``skills/``)
    - Houdini version detection via ``hou.applicationVersionString()``
    - Progressive loading helpers: :meth:`discover_skills`, :meth:`loaded_skill_count`

    Multi-instance / gateway
    ------------------------
    dcc-mcp-core implements an **auto-gateway** with first-wins port competition:
    the first Houdini process to bind the well-known port (8765) becomes the
    gateway; subsequent instances start on ephemeral ports and register
    themselves automatically.

    Progressive loading
    -------------------
    Skills can be discovered (metadata only, no Python import) and loaded
    on demand::

        server.discover_skills()             # fast: scan SKILL.md files
        server.load_skill("houdini-scene")   # lazy: import scripts only now
        server.unload_skill("houdini-scene") # unload to free memory

    Attributes:
        port: TCP port the server is listening on (updated after :meth:`start`).
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        extra_skill_paths: Optional[List[str]] = None,
        server_name: str = SERVER_NAME,
        server_version: str = SERVER_VERSION,
        gateway_port: Optional[int] = None,
        registry_dir: Optional[str] = None,
        dcc_version: Optional[str] = None,
        scene: Optional[str] = None,
        enable_gateway_failover: Optional[bool] = None,
        metrics_enabled: Optional[bool] = None,
        job_storage_path: Optional[str] = None,
        enable_workflows: Optional[bool] = None,
        options: Optional[HoudiniServerOptions] = None,
    ) -> None:
        from dcc_mcp_houdini import _env

        if options is None:
            options = HoudiniServerOptions(
                port=port,
                extra_skill_paths=extra_skill_paths,
                server_name=server_name,
                server_version=server_version,
                gateway_port=gateway_port,
                registry_dir=registry_dir,
                dcc_version=dcc_version,
                scene=scene,
                enable_gateway_failover=enable_gateway_failover,
                metrics_enabled=metrics_enabled,
                job_storage_path=job_storage_path,
                enable_workflows=enable_workflows,
            )

        super().__init__(options=options.to_core_options())

        self._extra_skill_paths: List[str] = list(options.extra_skill_paths or [])

        if _env.resolve_metrics_enabled(options.metrics_enabled):
            self._config.enable_prometheus = True
            logger.info("[%s] Prometheus /metrics endpoint enabled", _DCC_NAME)

        effective_job_path = _env.resolve_job_storage(options.job_storage_path)
        if effective_job_path:
            self._config.job_storage_path = effective_job_path
            logger.info("[%s] Job storage: %s", _DCC_NAME, effective_job_path)
        elif effective_job_path == "":
            self._config.job_storage_path = ""

        if _env.resolve_enable_workflows(options.enable_workflows):
            try:
                self._config.enable_workflows = True
                logger.info(
                    "[%s] Workflow engine enabled (workflows.run / .resume / .list_runs)",
                    _DCC_NAME,
                )
            except Exception as e:
                logger.warning("[%s] Workflow enable failed: %s", _DCC_NAME, e)


# ── public helpers (kept 1:1 with the old API) ─────────────────────────────

def start_server(
    port: int = DEFAULT_PORT,
    server_name: str = SERVER_NAME,
    server_version: str = SERVER_VERSION,
    **kwargs: Any,
) -> Any:
    """Convenience helper — mirrors the old module-level ``start_server()``."""
    from dcc_mcp_houdini._readiness import wait_until_ready

    opts = HoudiniServerOptions(
        port=port,
        server_name=server_name,
        server_version=server_version,
        **kwargs,
    )
    srv = HoudiniMcpServer(options=opts)
    handle = srv.start()
    wait_until_ready(srv, timeout=getattr(opts, "readiness_timeout_secs", 30))
    return handle


def stop_server() -> None:
    """Convenience helper — stops the global server instance."""
    from dcc_mcp_core.server_base import get_server

    srv = get_server()
    if srv is not None:
        srv.shutdown()
