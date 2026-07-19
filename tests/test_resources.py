"""Unit tests for the Houdini resource publisher.

Covers the ``houdini-help://`` producer degradation, the binder bind/unbind
lifecycle, and the trailing-edge throttling — all without a live Houdini.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock

import pytest

import dcc_mcp_houdini._resources as resources
from dcc_mcp_houdini._resources import (
    DEFAULT_SCENE_THROTTLE_SECS,
    ENV_RESOURCES,
    SCHEME_HOUDINI_HELP,
    HoudiniResourceBinder,
    _houdini_help_producer,
    _parse_path_uri,
    install_resources,
    resolve_enabled,
)


class TestResolveEnabled:
    def test_default_is_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_RESOURCES, raising=False)
        assert resolve_enabled() is True

    def test_zero_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_RESOURCES, "0")
        assert resolve_enabled() is False

    def test_explicit_argument_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_RESOURCES, "0")
        assert resolve_enabled(True) is True


class TestParsePathUri:
    def test_strips_scheme_and_splits(self) -> None:
        assert _parse_path_uri("houdini-help://Sop/box", scheme=SCHEME_HOUDINI_HELP) == ["Sop", "box"]

    def test_returns_none_when_scheme_mismatches(self) -> None:
        assert _parse_path_uri("scene://current", scheme=SCHEME_HOUDINI_HELP) is None


class TestHelpProducerWithoutHoudini:
    def test_help_returns_unavailable_envelope(self) -> None:
        out = _houdini_help_producer("houdini-help://Sop/box")
        assert out["mimeType"] == "application/json"
        body = json.loads(out["text"])
        assert body["status"] == "houdini_unavailable"

    def test_help_invalid_uri(self) -> None:
        out = _houdini_help_producer("houdini-help://")
        body = json.loads(out["text"])
        assert body["status"] == "invalid_uri"


class _RecordingResourceHandle:
    def __init__(self) -> None:
        self.scenes: List[Any] = []
        self.producers: Dict[str, Callable[[str], Dict[str, Any]]] = {}

    def set_scene(self, value: Any) -> None:
        self.scenes.append(value)

    def register_producer(self, scheme: str, callable_: Callable[[str], Dict[str, Any]]) -> None:
        self.producers[scheme] = callable_


class _FakeServer:
    def __init__(self) -> None:
        self.resource_handle = _RecordingResourceHandle()
        inner = MagicMock()
        inner.resources.return_value = self.resource_handle
        self._server = inner


class TestBinderBind:
    def test_bind_publishes_initial_snapshot_and_registers_producers(self) -> None:
        server = _FakeServer()
        snapshots: List[Dict[str, Any]] = []

        def provider() -> Dict[str, Any]:
            snap = {"dcc": "houdini", "scene": f"snap-{len(snapshots)}"}
            snapshots.append(snap)
            return snap

        binder = HoudiniResourceBinder(snapshot_provider=provider, event_installer=lambda cb: [])
        assert binder.bind(server) is True
        assert binder.handle is server.resource_handle
        assert binder.scene_publish_count == 1
        assert server.resource_handle.scenes == [{"dcc": "houdini", "scene": "snap-0"}]
        assert binder.registered_producers == [SCHEME_HOUDINI_HELP]

    def test_bind_without_snapshot_provider_skips_initial_publish(self) -> None:
        server = _FakeServer()
        binder = HoudiniResourceBinder()
        assert binder.bind(server) is True
        assert binder.scene_publish_count == 0

    def test_bind_is_idempotent(self) -> None:
        server = _FakeServer()
        binder = HoudiniResourceBinder(snapshot_provider=lambda: {"k": "v"})
        binder.bind(server)
        binder.bind(server)
        assert len(server.resource_handle.producers) == 1
        assert binder.scene_publish_count == 1

    def test_bind_returns_false_when_resources_unavailable(self) -> None:
        server = MagicMock()
        server._server.resources.side_effect = RuntimeError("not enabled")
        binder = HoudiniResourceBinder()
        assert binder.bind(server) is False
        assert binder.handle is None

    def test_install_scene_events_uses_injected_installer(self) -> None:
        server = _FakeServer()
        installed: List[Any] = []

        def installer(callback: Callable[[], None]) -> List[Any]:
            installed.append(callback)
            return ["handle-1"]

        binder = HoudiniResourceBinder(event_installer=installer)
        binder.bind(server)
        handles = binder.install_scene_events()
        assert handles == ["handle-1"]
        assert binder.scene_event_handles == ["handle-1"]
        assert installed

    def test_unbind_is_idempotent_and_clears_state(self) -> None:
        removed: List[Any] = []
        server = _FakeServer()
        binder = HoudiniResourceBinder(
            event_installer=lambda cb: [1, 2],
            event_remover=lambda handles: removed.extend(handles),
        )
        binder.bind(server)
        binder.install_scene_events()
        binder.unbind()
        binder.unbind()
        assert binder.scene_event_handles == []
        assert removed == [1, 2]


class TestThrottling:
    def test_event_after_throttle_window_publishes_immediately(self) -> None:
        server = _FakeServer()
        binder = HoudiniResourceBinder(
            snapshot_provider=lambda: {"event": "tick"},
            event_installer=lambda cb: [],
            throttle_secs=0.05,
        )
        binder.bind(server)
        baseline = binder.scene_publish_count
        time.sleep(0.1)
        binder._on_scene_event()
        assert binder.scene_publish_count == baseline + 1

    def test_burst_collapses_to_one_trailing_publish(self) -> None:
        server = _FakeServer()
        binder = HoudiniResourceBinder(
            snapshot_provider=lambda: {"event": "tick"},
            event_installer=lambda cb: [],
            throttle_secs=0.05,
        )
        binder.bind(server)
        baseline = binder.scene_publish_count
        for _ in range(50):
            binder._on_scene_event()
        assert binder.scene_publish_count == baseline
        time.sleep(0.2)
        assert binder.scene_publish_count == baseline + 1
        binder.unbind()

    def test_scene_events_drop_while_executor_busy(self) -> None:
        server = _FakeServer()
        busy = {"value": True}
        binder = HoudiniResourceBinder(
            snapshot_provider=lambda: {"event": "tick"},
            event_installer=lambda cb: [],
            busy_checker=lambda: busy["value"],
            throttle_secs=0.0,
        )
        binder.bind(server)
        baseline = binder.scene_publish_count
        binder._on_scene_event()
        assert binder.scene_publish_count == baseline
        busy["value"] = False
        binder._on_scene_event()
        assert binder.scene_publish_count == baseline + 1


class TestInstallResources:
    def test_returns_none_when_disabled_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_RESOURCES, "0")
        server = _FakeServer()
        assert install_resources(server) is None

    def test_returns_binder_with_producers_wired(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_RESOURCES, raising=False)
        server = _FakeServer()
        binder = install_resources(
            server,
            snapshot_provider=lambda: {"dcc": "houdini"},
            install_scene_events=False,
        )
        assert binder is not None
        assert binder.handle is server.resource_handle
        assert binder.scene_publish_count == 1

    def test_save_as_publishes_registry_scene_after_save(self, monkeypatch: pytest.MonkeyPatch) -> None:
        callbacks: List[Callable[..., None]] = []
        before_save = object()
        after_save = object()
        fake_hou = SimpleNamespace(
            hipFile=SimpleNamespace(addEventCallback=callbacks.append),
            hipFileEventType=SimpleNamespace(
                AfterClear=object(),
                AfterLoad=object(),
                AfterMerge=object(),
                AfterSave=after_save,
            ),
        )
        monkeypatch.setattr(resources, "_hou", lambda: fake_hou)

        main_thread = threading.get_ident()
        current_scene = {"path": "old.hip"}
        workers: List[threading.Thread] = []

        class RegistryServer(_FakeServer):
            def __init__(self) -> None:
                super().__init__()
                self.registry_scenes: List[str] = []

            def publish_capability_snapshot(self, *, reason: str) -> bool:
                if threading.get_ident() != main_thread:
                    return False
                self.registry_scenes.append(current_scene["path"])
                return True

        class ImmediateThreadTimer:
            def __init__(self, _delay: float, callback: Callable[[], None]) -> None:
                self.callback = callback
                self.daemon = False

            def start(self) -> None:
                worker = threading.Thread(target=self.callback)
                workers.append(worker)
                worker.start()

            def cancel(self) -> None:
                pass

        monkeypatch.setattr(resources.threading, "Timer", ImmediateThreadTimer)
        server = RegistryServer()
        binder = install_resources(
            server,
            snapshot_provider=lambda: {"scene": current_scene["path"]},
            throttle_secs=0.5,
        )
        assert binder is not None
        assert len(callbacks) == 1
        server.registry_scenes.clear()
        binder._last_publish_at = 0.0

        callbacks[0](before_save)
        current_scene["path"] = "new.hip"
        callbacks[0](after_save)
        for worker in workers:
            worker.join()

        assert server.registry_scenes == ["new.hip"]
        binder.unbind()


class TestModuleExports:
    def test_default_throttle_is_positive(self) -> None:
        assert DEFAULT_SCENE_THROTTLE_SECS > 0
