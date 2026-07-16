"""Houdini MCP server — embeds a Streamable HTTP MCP server inside Houdini."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core import DccServerOptions, HostExecutionBridge, MinimalModeConfig
from dcc_mcp_core.server_base import DccServerBase

from dcc_mcp_houdini.__version__ import __version__
from dcc_mcp_houdini._capability_manifest import (
    HoudiniCapabilityManifestBuilder,
    build_manifest_payload,
    register_capability_mcp_tool,
)
from dcc_mcp_houdini._context_snapshot import (
    HoudiniContextSnapshotProvider,
    collect_gateway_metadata,
)
from dcc_mcp_houdini._skill_loader import build_minimal_mode_config
from dcc_mcp_houdini._version_probe import get_houdini_version_string

logger = logging.getLogger(__name__)

SERVER_NAME = "dcc-mcp-houdini"
SERVER_VERSION = __version__
DEFAULT_PORT = 0

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

    port: Optional[int] = None
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
            bridge_dispatcher = dispatcher
            if host_dispatcher is not None:
                from dcc_mcp_houdini.host import HoudiniInlineCallableDispatcher

                bridge_dispatcher = HoudiniInlineCallableDispatcher()
            execution_bridge = HostExecutionBridge(
                dispatcher=bridge_dispatcher,
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
        port: Optional[int] = None,
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

        # FileRegistry self-registration is controlled by gateway_port in core.
        # Keep explicit gateway_port=0 as the opt-out, but do not let the
        # failover flag suppress registration for live discovery.
        if options.gateway_port == 0:
            self._config.gateway_port = 0

        from dcc_mcp_houdini._readiness import install_readiness

        self.readiness = install_readiness(self)

        # ── Context snapshot + capability manifest ──────────────────────
        # Houdini-specific context provider feeds both the core post-tool
        # ``append_context_snapshot`` wrapper and the per-DCC ``/v1/context``
        # REST endpoint.  Wrapped so a missing core API never breaks startup.
        self._snapshot_provider_impl: HoudiniContextSnapshotProvider = HoudiniContextSnapshotProvider()
        try:
            self.set_context_snapshot_provider(self._snapshot_provider_impl)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] set_context_snapshot_provider failed: %s", _DCC_NAME, exc)

        self._capability_builder: HoudiniCapabilityManifestBuilder = HoudiniCapabilityManifestBuilder(
            dcc_name=_DCC_NAME,
            skill_lister=self.list_skills,
            action_lister=self._list_actions_safe,
            is_loaded=self.is_skill_loaded,
            skill_info_lister=self._skill_info_safe,
        )

        # Populated by :meth:`register_builtin_actions`.
        self._project_tools: Any = None
        self._resources: Any = None

        # ── Morphology-aware semantic recall (opt-in) ───────────────────
        try:
            from dcc_mcp_houdini._semantic_index import build_semantic_index

            self._semantic = build_semantic_index()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] semantic index init failed: %s", _DCC_NAME, exc)
            self._semantic = None
        if self._semantic is not None:
            logger.info("[%s] semantic skill recall enabled (embedder=%s)", _DCC_NAME, self._semantic.embedder_kind)

    def _list_actions_safe(self) -> List[Any]:
        """Best-effort ``list_actions`` for the capability builder."""
        try:
            return list(self.list_actions())
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] list_actions failed: %s", _DCC_NAME, exc)
            return []

    def _skill_info_safe(self, name: str) -> Any:
        """Best-effort ``get_skill_info`` for the capability builder."""
        try:
            return self.get_skill_info(name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] get_skill_info(%r) failed: %s", _DCC_NAME, name, exc)
            return None

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

        # ── Core integrations (parity with Maya's registration phases) ───
        # Each step degrades gracefully: an unavailable core API or a
        # registration failure is logged at debug and never breaks startup.
        self._register_recipes_tools(extra_skill_paths, include_bundled)
        self._register_skill_reference_docs_tools(extra_skill_paths, include_bundled)
        self._register_introspect_tools()
        self._register_feedback_tool()
        self._register_qt_ui_inspector()
        self._register_capability_manifest_tool()
        self._attach_project_tools()
        self._attach_resources()

    # ── Core integration wiring (optional / graceful) ───────────────────

    def _scan_skill_metadata_for_sidecars(
        self,
        extra_skill_paths: Optional[List[str]],
        include_bundled: bool,
    ) -> List[Any]:
        """Return ``SkillMetadata`` list aligned with ``collect_skill_search_paths``."""
        from dcc_mcp_core import scan_and_load_lenient

        paths = self.collect_skill_search_paths(
            extra_paths=extra_skill_paths if extra_skill_paths is not None else self._extra_skill_paths,
            include_bundled=include_bundled,
            filter_existing=True,
        )
        extra = paths if paths else None
        skills, _skipped = scan_and_load_lenient(extra_paths=extra, dcc_name=_DCC_NAME)
        return skills

    def _register_skill_metadata_tools(
        self,
        register_fn: Any,
        kind: str,
        extra_skill_paths: Optional[List[str]],
        include_bundled: bool,
    ) -> None:
        try:
            skills = self._scan_skill_metadata_for_sidecars(extra_skill_paths, include_bundled)
            register_fn(self._server, skills=skills, dcc_name=_DCC_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] %s tools failed: %s", _DCC_NAME, kind, exc)

    def _register_recipes_tools(
        self,
        extra_skill_paths: Optional[List[str]] = None,
        include_bundled: bool = True,
    ) -> None:
        """Register ``recipes__*`` tools for ``metadata.dcc-mcp.recipes`` sidecars."""
        try:
            from dcc_mcp_core.recipes import register_recipes_tools
        except ImportError as exc:
            logger.debug("[%s] recipes tools skipped (import): %s", _DCC_NAME, exc)
            return
        self._register_skill_metadata_tools(register_recipes_tools, "recipes", extra_skill_paths, include_bundled)

    def _register_skill_reference_docs_tools(
        self,
        extra_skill_paths: Optional[List[str]] = None,
        include_bundled: bool = True,
    ) -> None:
        """Register ``skill_refs__*`` for sibling reference Markdown/text docs."""
        try:
            from dcc_mcp_core.skill_reference_docs import register_skill_reference_docs_tools
        except ImportError as exc:
            logger.debug("[%s] skill_refs tools skipped (import): %s", _DCC_NAME, exc)
            return
        self._register_skill_metadata_tools(
            register_skill_reference_docs_tools,
            "skill_refs",
            extra_skill_paths,
            include_bundled,
        )

    def _register_introspect_tools(self) -> None:
        """Register the core ``dcc_introspect__*`` runtime-introspection tools."""
        try:
            from dcc_mcp_core import register_introspect_tools
        except ImportError as exc:
            logger.debug("[%s] introspect tools skipped (import): %s", _DCC_NAME, exc)
            return
        try:
            register_introspect_tools(self._server, dcc_name=_DCC_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] introspect tools failed: %s", _DCC_NAME, exc)

    def _register_feedback_tool(self) -> None:
        """Register the core ``dcc_feedback__report`` tool."""
        try:
            from dcc_mcp_core import register_feedback_tool
        except ImportError as exc:
            logger.debug("[%s] feedback tool skipped (import): %s", _DCC_NAME, exc)
            return
        try:
            register_feedback_tool(self._server, dcc_name=_DCC_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] feedback tool failed: %s", _DCC_NAME, exc)

    def _register_qt_ui_inspector(self) -> None:
        """Adopt the shared core ``qt_ui_inspector__*`` tools (main-thread routed)."""
        try:
            from dcc_mcp_houdini._qt_inspector import register_houdini_qt_ui_inspector

            register_houdini_qt_ui_inspector(self, dcc_name=_DCC_NAME, dispatcher=self._houdini_dispatcher)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] qt-ui-inspector registration failed: %s", _DCC_NAME, exc)

    def _register_capability_manifest_tool(self) -> None:
        try:
            register_capability_mcp_tool(self, builder=self._capability_builder)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] capability manifest MCP tool registration failed: %s", _DCC_NAME, exc)

    def _attach_project_tools(self) -> None:
        try:
            from dcc_mcp_houdini import _project_tools

            self._project_tools = _project_tools.attach_to_server(self)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] project tools registration failed: %s", _DCC_NAME, exc)

    def _attach_resources(self) -> None:
        try:
            from dcc_mcp_houdini import _resources

            self._resources = _resources.install_resources(
                self,
                snapshot_provider=self._snapshot_provider_impl.collect,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] resources registration failed: %s", _DCC_NAME, exc)

    def build_capability_manifest(self, *, loaded_only: bool = False) -> Dict[str, Any]:
        """Return the compact Houdini capability manifest as a dict."""
        records = self._capability_builder.build()
        if loaded_only:
            records = [r for r in records if r.loaded]
        instance_id = getattr(self, "instance_id", None)
        scene = getattr(self._config, "scene", None)
        version = getattr(self._config, "dcc_version", None)
        return build_manifest_payload(
            records,
            dcc_name=_DCC_NAME,
            dcc_version=version,
            scene=scene,
            instance_id=instance_id,
        )

    def publish_capability_snapshot(self, *, reason: str = "manual") -> bool:
        """Push current Houdini context into the gateway registry (best effort)."""
        if not self.is_running:
            return False
        gateway_port = getattr(self._config, "gateway_port", 0)
        if not gateway_port or gateway_port <= 0:
            return False
        try:
            meta = collect_gateway_metadata(self._snapshot_provider_impl)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] capability snapshot: provider failed: %s", _DCC_NAME, exc)
            return False
        if not any((meta.get("scene"), meta.get("version"), meta.get("display_name"))):
            logger.debug("[%s] capability snapshot (%s): skipped — no actionable state", _DCC_NAME, reason)
            return False
        try:
            ok = self.update_gateway_metadata(
                scene=meta.get("scene"),
                version=meta.get("version"),
                documents=meta.get("documents"),
                display_name=meta.get("display_name"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] update_gateway_metadata failed (%s): %s", _DCC_NAME, reason, exc)
            return False
        return bool(ok)

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
            base = list(
                self._server.search_skills(
                    query=query,
                    tags=tags_list,
                    dcc=dcc_name,
                    scope=scope,
                    limit=limit,
                )
            )
        except TypeError:
            base = list(self._server.search_skills(query=query, tags=tags_list, dcc=dcc_name))

        # When the opt-in semantic index is enabled, augment the canonical BM25
        # results with morphology recalls. Base ordering is preserved (promote,
        # never demote); vector-only hits are appended.
        if self._semantic is not None and query:
            try:
                return self._semantic.augment(base, query, self.list_skills(), limit=limit)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[%s] semantic augment failed: %s", _DCC_NAME, exc)
        return base

    # Alias mirroring Maya's public ``search_skills`` surface.
    search_skills = find_skills

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
        if self._resources is not None:
            try:
                self._resources.unbind()
            except Exception as exc:  # noqa: BLE001
                logger.debug("[%s] resources.unbind failed: %s", _DCC_NAME, exc)

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
    port: Optional[int] = None,
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
