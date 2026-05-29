"""Houdini integration for ``dcc_mcp_core.register_project_tools``.

Mirrors :mod:`dcc_mcp_maya._project_tools`.  Wires the four project-persistence
MCP/REST tools from ``dcc-mcp-core``:

* ``project_save``   — persist current Houdini project state to ``.dcc-mcp/project.json``
* ``project_load``   — read an existing ``project.json`` back
* ``project_resume`` — return the rehydration payload an agent needs to restore
  scene, assets, active skills, tool groups and checkpoint IDs
* ``project_status`` — pure-read snapshot of the current state

Design notes (SOLID)
--------------------
* **Single Responsibility** — only orchestration: resolve the *current*
  Houdini hip file (so agents can call ``project_save`` with no arguments while
  inside Houdini) and forward to ``register_project_tools``.
* **Open/Closed** — the scene resolver is injectable
  (:class:`HoudiniSceneResolver`).  Tests subclass it to fake a hip path
  without touching ``hou``.
* **Dependency Inversion** — scene resolution is isolated behind
  :class:`HoudiniSceneResolver`, while core project persistence is used via its
  public ``register_project_tools`` contract.

Opt-out
-------
Set ``DCC_MCP_HOUDINI_PROJECT_TOOLS=0`` to skip registration.  Default is
**enabled** because the four tools are pure filesystem operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from dcc_mcp_core import DccProject, register_project_tools

from dcc_mcp_houdini._env import ENV_PROJECT_TOOLS, resolve_project_tools_enabled

logger = logging.getLogger(__name__)

_DCC_NAME = "houdini"

__all__ = [
    "ENV_PROJECT_TOOLS",
    "HoudiniSceneResolver",
    "ProjectToolsIntegration",
    "attach_to_server",
    "resolve_enabled",
]

# ``resolve_enabled`` kept as a module-level alias for parity with Maya tests.
resolve_enabled = resolve_project_tools_enabled


# ---------------------------------------------------------------------------
# Scene resolution strategy
# ---------------------------------------------------------------------------


class HoudiniSceneResolver:
    """Resolve the *current* Houdini hip file path, if one is saved.

    Returning ``None`` is a first-class signal — :func:`bind` then skips
    binding a default project so the four MCP tools require an explicit
    ``scene_path`` / ``project_dir`` argument from the caller.

    The default implementation calls ``hou.hipFile.path()`` inside a guarded
    import block so this module remains usable outside Houdini (unit tests,
    headless ``hython`` before a hip is loaded, gateway-only deployments).
    """

    def current_scene(self) -> Optional[str]:
        """Return the absolute hip path, or ``None`` when unavailable/unsaved."""
        try:
            import hou  # noqa: PLC0415
        except Exception:  # noqa: BLE001 — Houdini unavailable
            return None
        try:
            if not bool(hou.hipFile.hasFile()):
                return None
            scene = hou.hipFile.path()
        except Exception as exc:  # noqa: BLE001 — Houdini in odd state
            logger.debug("HoudiniSceneResolver: hou.hipFile.path() failed: %s", exc)
            return None
        scene = (scene or "").strip()
        return scene or None


# ---------------------------------------------------------------------------
# Integration object
# ---------------------------------------------------------------------------


class ProjectToolsIntegration:
    """Bind ``register_project_tools`` against a :class:`HoudiniMcpServer`."""

    def __init__(
        self,
        *,
        dcc_name: str = _DCC_NAME,
        scene_resolver: Optional[HoudiniSceneResolver] = None,
    ) -> None:
        self.dcc_name = dcc_name
        self.scene_resolver = scene_resolver or HoudiniSceneResolver()
        self.bound_scene: Optional[str] = None
        self.bound_project: Any = None
        self.registered: bool = False

    # ── Public API ──────────────────────────────────────────────────────

    def bind(
        self,
        server: Any,
        *,
        project_factory: Optional[Callable[[str], Any]] = None,
        explicit_project: Any = None,
    ) -> bool:
        """Register the four project tools on *server*.

        Returns ``True`` when the four tools were registered, ``False`` when the
        inner server is unavailable or registration fails.
        """
        inner = self._inner_server(server)
        if inner is None:
            return False

        project = explicit_project
        if project is None:
            scene = self._safe_resolve_scene()
            if scene:
                factory = project_factory or DccProject.open
                try:
                    project = factory(scene)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "ProjectToolsIntegration.bind: DccProject.open(%s) failed: %s",
                        scene,
                        exc,
                    )
                    project = None

        try:
            register_project_tools(inner, dcc_name=self.dcc_name, project=project)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ProjectToolsIntegration.bind: register_project_tools raised: %s",
                exc,
            )
            return False

        self.bound_scene = getattr(project, "state", None) and project.state.scene_path
        self.bound_project = project
        self.registered = True
        logger.info(
            "[%s] project tools registered (default scene=%s)",
            self.dcc_name,
            self.bound_scene or "<none>",
        )
        return True

    # ── Internals ───────────────────────────────────────────────────────

    @staticmethod
    def _inner_server(server: Any) -> Any:
        """Return the inner Rust ``McpHttpServer`` (or ``None``).

        ``register_project_tools`` calls ``server.registry`` *and*
        ``server.register_handler``.  Only the inner ``_server`` exposes both,
        so we never duck-type the wrapper (that would register tools but leave
        their handlers unwired → silent 404 at call time).
        """
        inner = getattr(server, "_server", None)
        if inner is None:
            return None
        if not hasattr(inner, "register_handler") or not hasattr(inner, "registry"):
            return None
        return inner

    def _safe_resolve_scene(self) -> Optional[str]:
        """Run the scene resolver, swallowing any unexpected error."""
        try:
            scene = self.scene_resolver.current_scene()
        except Exception as exc:  # noqa: BLE001
            logger.debug("ProjectToolsIntegration: scene resolver raised: %s", exc)
            return None
        if not scene:
            return None
        try:
            scene = str(Path(scene))
        except Exception:  # noqa: BLE001
            scene = str(scene)
        return scene


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def attach_to_server(
    server: Any,
    *,
    enabled: Optional[bool] = None,
    dcc_name: str = _DCC_NAME,
    scene_resolver: Optional[HoudiniSceneResolver] = None,
    project_factory: Optional[Callable[[str], Any]] = None,
    explicit_project: Any = None,
) -> Optional[ProjectToolsIntegration]:
    """One-shot helper used by :meth:`HoudiniMcpServer.register_builtin_actions`.

    Returns the :class:`ProjectToolsIntegration` instance when registration
    succeeded, or ``None`` when the env var disabled the surface or
    registration failed.
    """
    if not resolve_project_tools_enabled(enabled):
        return None
    integration = ProjectToolsIntegration(
        dcc_name=dcc_name,
        scene_resolver=scene_resolver,
    )
    if integration.bind(
        server,
        project_factory=project_factory,
        explicit_project=explicit_project,
    ):
        return integration
    return None
