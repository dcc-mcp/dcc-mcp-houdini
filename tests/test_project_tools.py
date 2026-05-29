"""Unit tests for :mod:`dcc_mcp_houdini._project_tools`.

These cover the pure logic of :class:`ProjectToolsIntegration`,
:class:`HoudiniSceneResolver`, env-var resolution, and the defensive paths —
all without a live Houdini or a running server.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

import dcc_mcp_houdini
from dcc_mcp_houdini import (
    HoudiniSceneResolver,
    ProjectToolsIntegration,
    attach_project_tools,
)
from dcc_mcp_houdini._project_tools import ENV_PROJECT_TOOLS, resolve_enabled


class TestEnvResolution(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(ENV_PROJECT_TOOLS, None)

    def tearDown(self) -> None:
        os.environ.pop(ENV_PROJECT_TOOLS, None)
        if self._saved is not None:
            os.environ[ENV_PROJECT_TOOLS] = self._saved

    def test_default_is_enabled(self) -> None:
        self.assertTrue(resolve_enabled(None))

    def test_env_zero_disables(self) -> None:
        os.environ[ENV_PROJECT_TOOLS] = "0"
        self.assertFalse(resolve_enabled(None))

    def test_env_one_enables(self) -> None:
        os.environ[ENV_PROJECT_TOOLS] = "1"
        self.assertTrue(resolve_enabled(None))

    def test_explicit_true_overrides_env_zero(self) -> None:
        os.environ[ENV_PROJECT_TOOLS] = "0"
        self.assertTrue(resolve_enabled(True))

    def test_explicit_false_overrides_env_one(self) -> None:
        os.environ[ENV_PROJECT_TOOLS] = "1"
        self.assertFalse(resolve_enabled(False))


class _StaticSceneResolver(HoudiniSceneResolver):
    def __init__(self, scene: Optional[str]) -> None:
        self._scene = scene
        self.calls = 0

    def current_scene(self) -> Optional[str]:
        self.calls += 1
        return self._scene


class _RaisingSceneResolver(HoudiniSceneResolver):
    def current_scene(self) -> Optional[str]:
        raise RuntimeError("hou.hipFile blew up")


class TestHoudiniSceneResolverDefault(unittest.TestCase):
    def test_returns_none_outside_houdini(self) -> None:
        resolver = HoudiniSceneResolver()
        self.assertIsNone(resolver.current_scene())


class TestProjectToolsIntegrationUnit(unittest.TestCase):
    def test_inner_server_picked_when_both_attrs_present(self) -> None:
        class _Inner:
            registry = object()

            def register_handler(self, name: str, fn: Any) -> None:
                pass

        class _Outer:
            _server = _Inner()

        outer = _Outer()
        self.assertIs(ProjectToolsIntegration._inner_server(outer), outer._server)

    def test_inner_server_returns_none_when_register_handler_missing(self) -> None:
        class _BadInner:
            registry = object()

        class _Outer:
            _server = _BadInner()

        self.assertIsNone(ProjectToolsIntegration._inner_server(_Outer()))

    def test_inner_server_returns_none_when_no_inner(self) -> None:
        class _Outer:
            pass

        self.assertIsNone(ProjectToolsIntegration._inner_server(_Outer()))

    def test_safe_resolve_scene_swallows_resolver_errors(self) -> None:
        integration = ProjectToolsIntegration(scene_resolver=_RaisingSceneResolver())
        self.assertIsNone(integration._safe_resolve_scene())

    def test_safe_resolve_scene_normalises_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            scene = os.path.join(td, "shot.hip")
            integration = ProjectToolsIntegration(scene_resolver=_StaticSceneResolver(scene))
            resolved = integration._safe_resolve_scene()
            self.assertEqual(Path(resolved), Path(scene))

    def test_bind_returns_false_when_inner_server_missing(self) -> None:
        integration = ProjectToolsIntegration(scene_resolver=_StaticSceneResolver(None))

        class _NoInner:
            pass

        self.assertFalse(integration.bind(_NoInner()))
        self.assertFalse(integration.registered)

    def test_attach_to_server_skipped_when_disabled(self) -> None:
        result = attach_project_tools(object(), enabled=False)
        self.assertIsNone(result)


class _FakeRegistry:
    def __init__(self):
        self.registered = []

    def register(self, name, **kwargs):
        self.registered.append((name, kwargs))


class _FakeInner:
    def __init__(self):
        self.registry = _FakeRegistry()
        self.handlers = {}

    def register_handler(self, name, handler):
        self.handlers[name] = handler


class _FakeServer:
    def __init__(self):
        self._server = _FakeInner()


class TestProjectToolsBindWithFakeScene(unittest.TestCase):
    """Bind succeeds against a duck-typed server and a fake scene resolver."""

    def test_bind_registers_project_tools_with_fake_scene(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            scene = os.path.join(td, "shot_010.hip")
            Path(scene).write_text("// hip\n", encoding="utf-8")
            integration = ProjectToolsIntegration(scene_resolver=_StaticSceneResolver(scene))
            server = _FakeServer()
            ok = integration.bind(server)
            self.assertTrue(ok)
            self.assertTrue(integration.registered)
            # The four project tools must be declared on the inner registry.
            declared = {name for name, _ in server._server.registry.registered}
            assert {"project_save", "project_load", "project_resume", "project_status"} <= declared

    def test_bind_without_scene_still_registers_tools(self) -> None:
        integration = ProjectToolsIntegration(scene_resolver=_StaticSceneResolver(None))
        server = _FakeServer()
        ok = integration.bind(server)
        self.assertTrue(ok)
        self.assertIsNone(integration.bound_project)


class TestPublicSurface(unittest.TestCase):
    def test_top_level_exports(self) -> None:
        for name in ("ENV_PROJECT_TOOLS", "HoudiniSceneResolver", "ProjectToolsIntegration", "attach_project_tools"):
            self.assertTrue(hasattr(dcc_mcp_houdini, name), f"dcc_mcp_houdini.{name} should be importable")
            self.assertIn(name, dcc_mcp_houdini.__all__, f"{name} missing from __all__")
