"""Houdini MCP server — embeds a Streamable HTTP MCP server inside Houdini."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core import DccServerOptions, HostExecutionBridge, MinimalModeConfig
from dcc_mcp_core.server_base import DccServerBase

from dcc_mcp_houdini.__version__ import __version__
from dcc_mcp_houdini._skill_loader import build_minimal_mode_config
from dcc_mcp_houdini._version_probe import get_houdini_version_string

logger = logging.getLogger(__name__)

SERVER_NAME = "dcc-mcp-houdini"
SERVER_VERSION = __version__
DEFAULT_PORT = 8765

_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_DCC_NAME = "houdini"


def _is_host_queue_dispatcher(dispatcher: Any) -> bool:
    """Return True for core BlockingDispatcher / QueueDispatcher-like objects."""
    return callable(getattr(dispatcher, "post", None)) and callable(getattr(dispatcher, "tick", None))


def _host_dispatcher_from(dispatcher: Any) -> Any:
    """Resolve a core host dispatcher hidden behind adapter wrappers."""
    if _is_host_queue_dispatcher(dispatcher):
        return dispatcher
    host_dispatcher = getattr(dispatcher, "host_dispatcher", None)
    if host_dispatcher is not None and _is_host_queue_dispatcher(host_dispatcher):
        return host_dispatcher
    return None


@dataclass
class HoudiniServerOptions:
    """Adapter-local options collapsed for the dcc-mcp-core 0.17+ server contract."""

    port: int = DEFAULT_PORT
    extra_skill_paths: Optional[List[str]] = None
    server_name: str = SERVER_NAME
    server_version: str = SERVER_VERSION
    gateway_port: Optional[int] = None
    registry_dir: Optional[str] = None
    dcc_version: Optional[str] = None
    scene: Optional[str] = None
    enable_gateway_failover: Optional[bool] = None
    metrics_enabled: Optional[bool] = None
    job_storage_path: Optional[str] = None
    enable_workflows: Optional[bool] = None
    dcc_pid: Optional[int] = None
    dcc_window_title: Optional[str] = None
    dcc_window_handle: Optional[int] = None
    snapshot_provider: Optional[Any] = None
    dispatcher: Optional[Any] = None
    execution_bridge: Optional[Any] = None

    def to_core_options(self) -> DccServerOptions:
        """Convert to core DccServerOptions using from_env()."""
        from dcc_mcp_houdini import _env

        dispatcher = self.dispatcher
        execution_bridge = self.execution_bridge
        if execution_bridge is None and dispatcher is not None:
            host_dispatcher = _host_dispatcher_from(dispatcher)
            execution_bridge = HostExecutionBridge(
                dispatcher=dispatcher,
                host_dispatcher=host_dispatcher,
                default_thread_affinity="main",
            )
            dispatcher = None
        elif execution_bridge is not None:
            dispatcher = None

        return DccServerOptions.from_env(
            dcc_name=_DCC_NAME,
            builtin_skills_dir=_BUILTIN_SKILLS_DIR,
            port=self.port,
            server_name=self.server_name,
            server_version=self.server_version,
            gateway_port=self.gateway_port,
            registry_dir=self.registry_dir,
            dcc_version=self.dcc_version,
            scene=self.scene,
            enable_gateway_failover=_env.resolve_enable_gateway_failover(self.enable_gateway_failover),
            enable_file_logging=True,
            enable_job_persistence=_env.resolve_job_storage(self.job_storage_path) is not None,
            enable_telemetry=True,
            dcc_pid=self.dcc_pid,
            dcc_window_title=self.dcc_window_title,
            dcc_window_handle=self.dcc_window_handle,
            snapshot_provider=self.snapshot_provider,
            dispatcher=dispatcher,
            execution_bridge=execution_bridge,
        )


class HoudiniMcpServer(DccServerBase):
    """MCP server embedded inside Houdini."""

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
        dispatcher: Optional[Any] = None,
        execution_bridge: Optional[Any] = None,
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
                dispatcher=dispatcher,
                execution_bridge=execution_bridge,
            )

        super().__init__(options=options.to_core_options())

        self._extra_skill_paths: List[str] = list(options.extra_skill_paths or [])
        self._houdini_dispatcher = self._dcc_dispatcher
        self._houdini_host: Any = None
        self.readiness: Any = None

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
                logger.info("[%s] Workflow engine enabled", _DCC_NAME)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] Workflow enable failed: %s", _DCC_NAME, exc)

        if options.gateway_port == 0 or (
            options.gateway_port is None and not _env.resolve_enable_gateway_failover(options.enable_gateway_failover)
        ):
            self._config.gateway_port = 0

        from dcc_mcp_houdini._readiness import install_readiness

        self.readiness = install_readiness(self)

    def _version_string(self) -> str:
        """Return the Houdini version via ``hou.applicationVersionString()``."""
        return get_houdini_version_string()

    @property
    def port(self) -> int:
        """TCP port the server is listening on."""
        if self._handle is not None:
            try:
                return int(self._handle.port)
            except Exception:
                pass
        return int(self._options.port)

    @property
    def mcp_url(self) -> str:
        """Return the MCP Streamable HTTP endpoint URL."""
        return f"http://127.0.0.1:{self.port}/mcp"

    def _collect_skill_paths(self) -> List[str]:
        """Collect existing skill search paths."""
        return self.collect_skill_search_paths(
            extra_paths=self._extra_skill_paths,
            filter_existing=True,
        )

    def register_builtin_actions(
        self,
        extra_skill_paths: list[str] | None = None,
        include_bundled: bool = True,
        minimal_mode: MinimalModeConfig | None = None,
    ) -> None:
        """Discover skills and apply minimal-mode progressive loading by default."""
        from dcc_mcp_houdini import _env

        if minimal_mode is None and _env.resolve_minimal_mode_enabled():
            minimal_mode = build_minimal_mode_config()
        super().register_builtin_actions(
            extra_skill_paths=extra_skill_paths,
            include_bundled=include_bundled,
            minimal_mode=minimal_mode,
        )

    def start(self, *, install_atexit_hook: bool = True) -> HoudiniMcpServer:
        """Start the MCP HTTP server. Returns *self* for chaining."""
        super().start(install_atexit_hook=install_atexit_hook)
        return self

    def discover_skills(self, extra_paths: Optional[List[str]] = None) -> int:
        """Scan skill directories and register tool metadata without importing scripts."""
        if self._handle is None:
            logger.warning("discover_skills called before server was started")
            return 0
        paths = self._collect_skill_paths()
        if extra_paths:
            paths = list(extra_paths) + paths
        count = self._server.discover(extra_paths=paths, dcc_name=_DCC_NAME)
        logger.debug("HoudiniMcpServer: discovered %d new skill(s)", count)
        return count

    def load_skill(self, skill_name: str) -> bool:
        """Load a skill by name — imports scripts and registers tools."""
        if self._handle is None:
            raise RuntimeError("Server is not running — call start() first")
        try:
            self._server.load_skill(skill_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("HoudiniMcpServer: load_skill(%r) failed: %s", skill_name, exc)
            return False
        logger.debug("HoudiniMcpServer: loaded skill %r", skill_name)
        return True

    def unload_skill(self, skill_name: str) -> bool:
        """Unload a skill, removing its tools from the registry."""
        if self._handle is None:
            raise RuntimeError("Server is not running — call start() first")
        try:
            self._server.unload_skill(skill_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("HoudiniMcpServer: unload_skill(%r) failed: %s", skill_name, exc)
            return False
        logger.debug("HoudiniMcpServer: unloaded skill %r", skill_name)
        return True

    def list_skills(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all discovered skills with their load status."""
        if self._handle is None:
            return []
        return list(self._server.list_skills(status=status))

    def find_skills(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        dcc: Optional[str] = None,
        scope: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for skills matching the given criteria."""
        if self._handle is None:
            return []
        tags_list: List[str] = tags if tags is not None else []
        dcc_name: str = dcc if dcc is not None else _DCC_NAME
        try:
            return list(
                self._server.search_skills(
                    query=query,
                    tags=tags_list,
                    dcc=dcc_name,
                    scope=scope,
                    limit=limit,
                )
            )
        except TypeError:
            return list(self._server.search_skills(query=query, tags=tags_list, dcc=dcc_name))

    def is_skill_loaded(self, skill_name: str) -> bool:
        """Return ``True`` if the named skill is currently loaded."""
        if self._handle is None:
            return False
        return self._server.is_loaded(skill_name)

    def loaded_skill_count(self) -> int:
        """Return the number of currently loaded skills."""
        if self._handle is None:
            return 0
        return self._server.loaded_count()

    def attach_host(self, host: Any) -> None:
        """Store the active :class:`~dcc_mcp_houdini.host.HoudiniHost` for teardown."""
        self._houdini_host = host

    def stop(self) -> None:
        """Stop the MCP server and detach the Houdini host adapter."""
        host = self._houdini_host
        if host is not None:
            try:
                host.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] host stop failed: %s", _DCC_NAME, exc)
            self._houdini_host = None
        super().stop()


_server_instance: Optional[HoudiniMcpServer] = None
_host_instance: Any = None


def start_server(
    port: int = DEFAULT_PORT,
    extra_skill_paths: Optional[List[str]] = None,
    register_builtins: bool = True,
    include_bundled: bool = True,
    enable_hot_reload: bool = False,
    gateway_port: Optional[int] = None,
    registry_dir: Optional[str] = None,
    dcc_version: Optional[str] = None,
    scene: Optional[str] = None,
    enable_gateway_failover: Optional[bool] = None,
    metrics_enabled: Optional[bool] = None,
    job_storage_path: Optional[str] = None,
    enable_workflows: Optional[bool] = None,
    wait_ready: bool = True,
    readiness_timeout_secs: Optional[int] = None,
) -> HoudiniMcpServer:
    """Start the Houdini MCP server (creates a process-level singleton)."""
    global _server_instance, _host_instance  # noqa: PLW0603

    if _server_instance is not None and _server_instance.is_running:
        return _server_instance

    from dcc_mcp_houdini.dispatcher import create_execution_stack

    dispatcher, host = create_execution_stack()
    _host_instance = host

    _server_instance = HoudiniMcpServer(
        port=port,
        extra_skill_paths=extra_skill_paths,
        gateway_port=gateway_port,
        registry_dir=registry_dir,
        dcc_version=dcc_version,
        scene=scene,
        enable_gateway_failover=enable_gateway_failover,
        metrics_enabled=metrics_enabled,
        job_storage_path=job_storage_path,
        enable_workflows=enable_workflows,
        dispatcher=dispatcher,
    )
    if host is not None:
        _server_instance.attach_host(host)

    if register_builtins:
        _server_instance.register_builtin_actions(include_bundled=include_bundled)
    if enable_hot_reload:
        _server_instance.enable_hot_reload()

    _server_instance.start()

    if wait_ready:
        from dcc_mcp_houdini._readiness import resolve_readiness_timeout_secs, wait_until_ready

        wait_until_ready(_server_instance, timeout=resolve_readiness_timeout_secs(readiness_timeout_secs) or 30)

    logger.info("[%s] MCP server listening on %s", _DCC_NAME, _server_instance.mcp_url)
    return _server_instance


def stop_server() -> None:
    """Stop the running Houdini MCP server."""
    global _server_instance, _host_instance  # noqa: PLW0603
    if _server_instance is None:
        return
    _server_instance.stop()
    _server_instance = None
    _host_instance = None


def get_server() -> Optional[HoudiniMcpServer]:
    """Return the current server instance, or ``None`` if not started."""
    return _server_instance
