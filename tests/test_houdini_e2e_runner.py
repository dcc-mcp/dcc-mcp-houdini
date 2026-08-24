"""Non-Houdini regressions for the licensed live E2E worker lifecycle."""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "run_houdini_e2e.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_houdini_e2e", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    hou = SimpleNamespace(applicationVersionString=lambda: "test")
    with patch.dict(sys.modules, {"hou": hou}):
        spec.loader.exec_module(module)
    return module


def test_headless_e2e_runs_one_client_worker_and_signals_shutdown() -> None:
    module = _load_script()
    owner_thread = threading.get_ident()
    observed = {}

    def serve_headless(*, stop_event, on_started, **kwargs):
        observed["owner_thread"] = threading.get_ident()
        on_started("server")
        assert stop_event.wait(timeout=1)
        observed["stop_signaled"] = stop_event.is_set()

    def client(server):
        observed["server"] = server
        observed["client_thread"] = threading.get_ident()

    module._serve_with_client_worker(serve_headless, client, join_timeout=1)

    assert observed == {
        "owner_thread": owner_thread,
        "server": "server",
        "client_thread": observed["client_thread"],
        "stop_signaled": True,
    }
    assert observed["client_thread"] != owner_thread


def test_headless_e2e_rethrows_worker_failure_on_owner_thread() -> None:
    module = _load_script()
    observed = {}

    class ClientFailure(RuntimeError):
        pass

    def serve_headless(*, stop_event, on_started, **kwargs):
        on_started("server")
        assert stop_event.wait(timeout=1)
        observed["stop_signaled"] = stop_event.is_set()

    def client(_server):
        raise ClientFailure("client failed")

    with pytest.raises(ClientFailure, match="client failed"):
        module._serve_with_client_worker(serve_headless, client, join_timeout=1)

    assert observed["stop_signaled"] is True
