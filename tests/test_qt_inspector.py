"""Unit tests for :mod:`dcc_mcp_houdini._qt_inspector`.

No live Houdini / Qt is required: we verify env gating, the graceful path when
the inner server is missing, and that the main-thread proxy wraps handlers and
marshals through an injected dispatcher.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, List

import pytest

from dcc_mcp_houdini._qt_inspector import (
    ENV_QT_UI_INSPECTOR,
    _MainThreadHandlerProxy,
    _make_marshaller,
    register_houdini_qt_ui_inspector,
    resolve_qt_ui_inspector_enabled,
)


class TestEnvGating:
    def test_default_enabled(self) -> None:
        assert resolve_qt_ui_inspector_enabled({}) is True

    @pytest.mark.parametrize("token", ["0", "false", "no", "off"])
    def test_disabled_tokens(self, token: str) -> None:
        assert resolve_qt_ui_inspector_enabled({ENV_QT_UI_INSPECTOR: token}) is False

    def test_disabled_env_short_circuits_registration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_QT_UI_INSPECTOR, "0")

        class _Server:
            _server = object()

        assert register_houdini_qt_ui_inspector(_Server()) is False


class TestMissingInner:
    def test_missing_inner_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_QT_UI_INSPECTOR, raising=False)

        class _Server:
            _server = None

        assert register_houdini_qt_ui_inspector(_Server()) is False


class _FakeDispatcher:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def dispatch_callable(self, func: Callable[[], Any], **kwargs: Any) -> Any:
        self.calls.append(kwargs.get("action_name", ""))
        return func()


class TestMarshaller:
    def test_inline_when_no_dispatcher(self) -> None:
        marshal = _make_marshaller(None)
        assert marshal(lambda: 42) == 42

    def test_inline_when_on_main_thread(self) -> None:
        dispatcher = _FakeDispatcher()
        marshal = _make_marshaller(dispatcher)
        # The test runs on the main thread, so the marshaller must run inline.
        assert marshal(lambda: "ok") == "ok"
        assert dispatcher.calls == []

    def test_dispatches_from_worker_thread(self) -> None:
        dispatcher = _FakeDispatcher()
        marshal = _make_marshaller(dispatcher)
        result: List[Any] = []

        def worker() -> None:
            result.append(marshal(lambda: "marshalled"))

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert result == ["marshalled"]
        assert dispatcher.calls == ["qt_ui_inspector"]

    def test_degrades_to_inline_when_dispatch_raises(self) -> None:
        class _BoomDispatcher:
            def dispatch_callable(self, func: Callable[[], Any], **kwargs: Any) -> Any:
                raise RuntimeError("queue closed")

        marshal = _make_marshaller(_BoomDispatcher())
        result: List[Any] = []

        def worker() -> None:
            result.append(marshal(lambda: "fallback"))

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert result == ["fallback"]


class TestProxy:
    def test_proxy_wraps_register_handler(self) -> None:
        registered = {}

        class _Inner:
            registry = object()

            def register_handler(self, name: str, handler: Callable[[Any], Any]) -> None:
                registered[name] = handler

        dispatcher = _FakeDispatcher()
        proxy = _MainThreadHandlerProxy(_Inner(), _make_marshaller(dispatcher))
        assert proxy.registry is _Inner.registry

        proxy.register_handler("t", lambda params: {"params": params})
        # The wrapped handler must still produce the original result.
        out = registered["t"]({"a": 1})
        assert out == {"params": {"a": 1}}


class TestRegistrationWithFakeCore:
    def test_registers_via_core_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_QT_UI_INSPECTOR, raising=False)

        captured = {}

        def _fake_register(server: Any, *, dcc_name: str = "dcc") -> None:
            captured["server"] = server
            captured["dcc_name"] = dcc_name

        import sys
        import types

        mod = types.ModuleType("dcc_mcp_core.skills.qt_ui_inspector")
        mod.register_qt_ui_inspector = _fake_register
        monkeypatch.setitem(sys.modules, "dcc_mcp_core.skills.qt_ui_inspector", mod)

        class _Inner:
            registry = object()

            def register_handler(self, name, handler):
                pass

        class _Server:
            _server = _Inner()
            _houdini_dispatcher = _FakeDispatcher()

        ok = register_houdini_qt_ui_inspector(_Server(), dcc_name="houdini")
        assert ok is True
        assert captured["dcc_name"] == "houdini"
        assert isinstance(captured["server"], _MainThreadHandlerProxy)
