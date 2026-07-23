"""Regression tests for chunked and durable node cooks (issue #183)."""

from __future__ import annotations

import importlib.util
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dcc_mcp_core import ChunkedRunner, HostExecutionBridge
from skill_loader import skill_script_import_context

from dcc_mcp_houdini import _cook_jobs, _cook_worker
from dcc_mcp_houdini._status_io import read_status, write_status
from dcc_mcp_houdini.host import HoudiniUiDispatcher

_SCRIPT = (
    Path(__file__).parent.parent
    / "src"
    / "dcc_mcp_houdini"
    / "skills"
    / "houdini-nodes"
    / "scripts"
    / "cook_nodes_chunked.py"
)


def _load_chunked_script():
    spec = importlib.util.spec_from_file_location("houdini_nodes_chunked_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_launch_cook_job_returns_durable_worker_job(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    initial = {"job_id": "a" * 32, "state": "queued"}
    with patch.object(
        _cook_jobs._rop_jobs,
        "_validate_saved_hip",
        return_value=(tmp_path / "scene.hip", True),
    ), patch.object(
        _cook_jobs._rop_jobs,
        "_hython_executable",
        return_value=tmp_path / "hython",
    ), patch.object(
        _cook_jobs._isolated_jobs,
        "create_job",
        return_value=(initial, status_path),
    ), patch.object(
        _cook_jobs._isolated_jobs,
        "launch_job",
        return_value={**initial, "pid": 42},
    ) as launch:
        result = _cook_jobs.launch_cook_job(MagicMock(), "/obj/geo1/cache1", True)

    assert result["job_id"] == "a" * 32
    command = launch.call_args.args[1]
    assert command[2:5] == [str(tmp_path / "scene.hip"), "/obj/geo1/cache1", "1"]
    assert command[-1] == str(status_path)


def test_get_cook_job_remains_queryable_after_adapter_ownership_is_lost(tmp_path: Path) -> None:
    with patch.object(_cook_jobs._isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        status, status_path = _cook_jobs._isolated_jobs.create_job(
            {"job_kind": "node_cook", "node_path": "/obj/geo1/cache1"}
        )
        status["state"] = "completed"
        write_status(status_path, status)
        _cook_jobs._isolated_jobs._PROCESS_HANDLES.clear()

        recovered = _cook_jobs.get_cook_job(status["job_id"])

    assert recovered["state"] == "completed"
    assert recovered["node_path"] == "/obj/geo1/cache1"
    assert recovered["owned_by_current_process"] is False


def test_get_cook_job_reports_live_elapsed_time_after_disconnect() -> None:
    status = {
        "job_id": "b" * 32,
        "job_kind": "node_cook",
        "state": "running",
        "started_at": 100.0,
        "owned_by_current_process": False,
    }
    with patch.object(_cook_jobs._isolated_jobs, "read_job", return_value=status), patch.object(
        _cook_jobs.time, "time", return_value=112.3456
    ):
        recovered = _cook_jobs.get_cook_job(status["job_id"])

    assert recovered["elapsed_secs"] == 12.346


def test_cook_worker_writes_terminal_status(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    write_status(status_path, {"job_id": "c" * 32, "job_kind": "node_cook", "state": "queued"})
    node = MagicMock()
    hou = SimpleNamespace(
        hipFile=SimpleNamespace(load=MagicMock()),
        node=lambda path: node if path == "/obj/geo1/cache1" else None,
    )
    argv = ["_cook_worker.py", str(tmp_path / "scene.hip"), "/obj/geo1/cache1", "1", str(status_path)]

    with patch.dict(sys.modules, {"hou": hou}), patch.object(sys, "argv", argv):
        _cook_worker.main()

    terminal = read_status(status_path)
    assert terminal["state"] == "completed"
    node.cook.assert_called_once_with(force=True)
    hou.hipFile.load.assert_called_once()


def test_chunked_cook_advances_one_node_per_step() -> None:
    first = MagicMock()
    second = MagicMock()
    hou = SimpleNamespace(node=lambda path: {"/obj/a": first, "/obj/b": second}.get(path))
    with patch.dict(sys.modules, {"hou": hou}):
        runner = _load_chunked_script().main(node_paths=["/obj/a", "/obj/b"], force=True)
        assert runner.step()
        first.cook.assert_called_once_with(force=True)
        second.cook.assert_not_called()
        assert not runner.step()
    second.cook.assert_called_once_with(force=True)


def test_houdini_bridge_auto_schedules_returned_chunked_runner() -> None:
    dispatcher = HoudiniUiDispatcher()
    bridge = HostExecutionBridge(dispatcher=dispatcher)
    calls = []

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            bridge.dispatch_callable,
            lambda: ChunkedRunner([lambda: calls.append("a"), lambda: calls.append("b")]),
            execution="async",
            job_strategy="chunked",
            job_id="job-183",
        )
        deadline = time.monotonic() + 2
        while not future.done() and time.monotonic() < deadline:
            dispatcher.drain_queue(20)
            time.sleep(0.001)

        assert future.result(timeout=0.1) == {"current": 2, "total": 2, "message": None}
    assert calls == ["a", "b"]
