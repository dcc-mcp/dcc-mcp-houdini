"""Regression tests for Houdini's budgeted UI-thread pump."""

from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeHoudiniUi:
    def __init__(self) -> None:
        self.callbacks = []

    def addEventLoopCallback(self, callback) -> None:
        self.callbacks.append(callback)

    def removeEventLoopCallback(self, callback) -> None:
        self.callbacks.remove(callback)


def _fake_hou(ui_available: bool = True):
    ui = _FakeHoudiniUi()
    return SimpleNamespace(isUIAvailable=lambda: ui_available, ui=ui), ui


def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not met before timeout")


def test_interactive_stack_uses_one_budgeted_core_ui_pump() -> None:
    from dcc_mcp_core import HostUiDispatcherBase

    from dcc_mcp_houdini.dispatcher import create_execution_stack

    hou, ui = _fake_hou()
    with patch.dict(sys.modules, {"hou": hou}):
        dispatcher, host = create_execution_stack()
        try:
            assert isinstance(dispatcher, HostUiDispatcherBase)
            assert host.is_running
            assert len(ui.callbacks) == 1

            host.start()
            assert len(ui.callbacks) == 1
        finally:
            host.stop()
            host.stop()

    assert ui.callbacks == []


def test_legacy_houdini_host_retains_headless_bootstrap_contract() -> None:
    from dcc_mcp_core.host import BlockingDispatcher

    from dcc_mcp_houdini.host import HoudiniHost

    stop = threading.Event()
    stop.set()
    HoudiniHost(BlockingDispatcher()).run_headless(stop_event=stop)


def test_event_loop_adapter_throttles_due_ticks_and_isolates_exceptions() -> None:
    from dcc_mcp_houdini.host import HoudiniEventLoopTimerAdapter

    clock = _FakeClock()
    hou, ui = _fake_hou()
    timer = HoudiniEventLoopTimerAdapter(clock=clock, error_retry_secs=0.1)
    calls = []

    def failing_tick():
        calls.append("failed")
        raise RuntimeError("boom")

    with patch.dict(sys.modules, {"hou": hou}):
        timer.install(failing_tick)
        timer.install(failing_tick)
        assert len(ui.callbacks) == 1

        ui.callbacks[0]()
        ui.callbacks[0]()
        assert calls == ["failed"]

        timer.install(lambda: calls.append("recovered") or 0.5)
        clock.advance(0.1)
        ui.callbacks[0]()
        ui.callbacks[0]()
        assert calls == ["failed", "recovered"]

        clock.advance(0.5)
        ui.callbacks[0]()
        assert calls == ["failed", "recovered", "recovered"]

        timer.install(lambda: timer.schedule_soon() or calls.append("wake") or 0.5)
        ui.callbacks[0]()
        ui.callbacks[0]()
        assert calls[-2:] == ["wake", "wake"]

        timer.uninstall()
        timer.uninstall()
        timer.install(lambda: 1.0)
        assert len(ui.callbacks) == 1
        timer.uninstall()

    assert ui.callbacks == []


def test_host_controller_applies_budget_and_exposes_overrun_stats(monkeypatch) -> None:
    from dcc_mcp_houdini.host import HoudiniEventLoopTimerAdapter, HoudiniUiDispatcher, HoudiniUiPump

    clock = _FakeClock()
    hou, ui = _fake_hou()
    dispatcher = HoudiniUiDispatcher()
    timer = HoudiniEventLoopTimerAdapter(clock=clock)
    host = HoudiniUiPump(dispatcher, budget_ms=4, timer_adapter=timer, clock=clock)
    budgets = []

    def drain_queue(budget_ms):
        budgets.append(budget_ms)
        clock.advance(0.009)
        return {"drained": 1, "remaining": 0, "elapsed_ms": 9.0, "overrun": True}

    monkeypatch.setattr(dispatcher, "drain_queue", drain_queue)
    with patch.dict(sys.modules, {"hou": hou}):
        host.start()
        ui.callbacks[0]()
        ui.callbacks[0]()

        assert budgets == [4]
        assert host.stats.ticks == 1
        assert host.stats.drained_jobs == 1
        assert host.stats.overrun_count == 1
        assert host.stats.last_elapsed_ms == 9.0

        clock.advance(0.05)
        ui.callbacks[0]()
        assert budgets == [4, 4]
        host.stop()


def test_ui_dispatcher_cancels_queued_work_and_survives_task_errors() -> None:
    from dcc_mcp_houdini.host import HoudiniUiDispatcher, HoudiniUiPump

    hou, ui = _fake_hou()
    dispatcher = HoudiniUiDispatcher()
    host = HoudiniUiPump(dispatcher)
    cancelled = []
    failed = []
    recovered = []

    with patch.dict(sys.modules, {"hou": hou}):
        host.start()

        cancel_thread = threading.Thread(
            target=lambda: cancelled.append(dispatcher.submit_callable("cancel-me", lambda: "never", affinity="main"))
        )
        cancel_thread.start()
        _wait_until(lambda: dispatcher.queue_size() == 1)
        assert dispatcher.cancel("cancel-me") is True
        cancel_thread.join(timeout=1)

        def fail() -> None:
            raise ValueError("task failed")

        fail_thread = threading.Thread(
            target=lambda: failed.append(dispatcher.submit_callable("fail", fail, affinity="main"))
        )
        fail_thread.start()
        _wait_until(lambda: dispatcher.queue_size() == 2)
        ui.callbacks[0]()
        fail_thread.join(timeout=1)

        ok_thread = threading.Thread(
            target=lambda: recovered.append(dispatcher.submit_callable("recover", lambda: "ok", affinity="main"))
        )
        ok_thread.start()
        _wait_until(lambda: dispatcher.queue_size() == 1)
        ui.callbacks[0]()
        ok_thread.join(timeout=1)
        host.stop()

    assert cancelled[0]["error"] == "Cancelled"
    assert failed[0]["error"] == "task failed"
    assert recovered[0]["output"] == "ok"


def test_pre_drain_check_failure_does_not_wedge_pump() -> None:
    """pre_drain_check returning False must NOT leave _next_due=inf.

    Regression test for the pump wedge fixed in PIP-2826: when
    pre_drain_check fails (returns False or raises), _callback() must
    reset _next_due under the lock so the next event-loop invocation
    can retry instead of being permanently blocked.
    """
    from dcc_mcp_houdini.host import HoudiniEventLoopTimerAdapter

    clock = _FakeClock()
    ticks = []
    check_results = [False, True]  # first check fails, second succeeds

    def _pre_drain() -> bool:
        return check_results.pop(0) if check_results else True

    adapter = HoudiniEventLoopTimerAdapter(
        clock=clock,
        pre_drain_check=_pre_drain,
    )
    hou, ui = _fake_hou()

    def _tick() -> float:
        ticks.append(clock())
        return 0.1

    with patch.dict(sys.modules, {"hou": hou}):
        adapter.install(_tick)

        # --- First callback: pre_drain returns False ---
        ui.callbacks[0]()
        # The tick should NOT have been called
        assert len(ticks) == 0
        # _next_due must be a finite retry value, NOT inf
        assert adapter._next_due == clock() + adapter._error_retry_secs, (
            f"Expected _next_due={clock() + adapter._error_retry_secs}, "
            f"got {adapter._next_due}"
        )

        # --- Advance past retry interval ---
        clock.advance(adapter._error_retry_secs)

        # --- Second callback: pre_drain returns True, pump should tick ---
        ui.callbacks[0]()
        assert len(ticks) == 1
        assert ticks[0] == clock()

        adapter.uninstall()


def test_pre_drain_check_exception_does_not_wedge_pump() -> None:
    """pre_drain_check raising an exception must NOT leave _next_due=inf."""
    from dcc_mcp_houdini.host import HoudiniEventLoopTimerAdapter

    clock = _FakeClock()
    ticks = []

    def _pre_drain() -> bool:
        raise RuntimeError("simulated pre_drain failure")

    adapter = HoudiniEventLoopTimerAdapter(
        clock=clock,
        pre_drain_check=_pre_drain,
    )
    hou, ui = _fake_hou()

    def _tick() -> float:
        ticks.append(clock())
        return 0.1

    with patch.dict(sys.modules, {"hou": hou}):
        adapter.install(_tick)

        # Callback: pre_drain raises → must not wedge
        ui.callbacks[0]()
        assert len(ticks) == 0
        assert adapter._next_due == clock() + adapter._error_retry_secs, (
            f"Expected _next_due={clock() + adapter._error_retry_secs}, "
            f"got {adapter._next_due}"
        )

        adapter.uninstall()
