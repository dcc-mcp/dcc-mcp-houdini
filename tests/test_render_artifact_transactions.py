"""Pure tests for staged no-clobber render publication."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

from dcc_mcp_houdini import _isolated_jobs, _render_artifacts, _rop_jobs, _status_io

_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-render" / "scripts"
)
_VALIDATOR = {
    "id": "openexr-structure-gate",
    "version": "1.0.0",
    "implementation_sha256": "a" * 64,
}


def _load_script(name: str) -> ModuleType:
    path = _SKILL_SCRIPTS / name
    spec = importlib.util.spec_from_file_location("transaction_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _MutableParm:
    def __init__(self, value: str):
        self.value = value
        self.set_calls = []

    def unexpandedString(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.set_calls.append(value)
        self.value = value


def _run_transaction_worker(
    tmp_path: Path,
    frames=(1, 2),
    produced=(1, 2),
    render_error=None,
    outputs=None,
    rop_inputs=(),
):
    module = _load_script("_render_worker.py")
    job_id = "1" * 32
    final_pattern = str(tmp_path / "beauty.$F4.exr")
    output_patterns = outputs or {"vm_picture": final_pattern}
    parms = {name: _MutableParm(pattern) for name, pattern in output_patterns.items()}
    rop = MagicMock()
    rop.parm.side_effect = lambda name: parms.get(name)
    rop.inputs.return_value = list(rop_inputs)
    rop.errors.return_value = []

    mock_hou = MagicMock()
    mock_hou.node.return_value = rop
    mock_hou.text.expandStringAtFrame.side_effect = lambda pattern, frame: pattern.replace(
        "$F4", "{:04d}".format(int(frame))
    )
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    status_path = tmp_path / "status.json"
    transaction = _render_artifacts.normalize_transaction_request({"mode": "staged_no_clobber"})
    frame_range = [frames[0], frames[-1], 1]
    transaction["requested_frames"] = _render_artifacts.integer_frames(frame_range)
    status_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "state": "queued",
                "job_kind": "render",
                "stdout_path": str(stdout),
                "stderr_path": str(stderr),
                "artifact_transaction": transaction,
            }
        ),
        encoding="utf-8",
    )

    def render(_rop, _frame_range):
        for frame in produced:
            staged = Path(mock_hou.text.expandStringAtFrame(parms["vm_picture"].value, frame))
            staged.write_bytes("frame {}".format(frame).encode("ascii"))
        if render_error:
            raise RuntimeError(render_error)
        return [float(frames[0]), float(frames[-1])], "render"

    argv = [
        "_render_worker.py",
        "scene.hip",
        "/out/mantra1",
        json.dumps(frame_range),
        str(status_path),
        json.dumps(final_pattern),
        json.dumps(False),
    ]
    with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(module.sys, "argv", argv), patch.object(
        module, "render_node", side_effect=render
    ):
        module.main()
    return json.loads(status_path.read_text(encoding="utf-8")), parms, mock_hou, final_pattern


def _completed_job(tmp_path: Path, count: int = 1, job_id: str = "2" * 32, stem: str = "beauty"):
    artifacts = []
    for frame in range(1, count + 1):
        final_path = tmp_path / "{}.{:04d}.exr".format(stem, frame)
        staged_path = tmp_path / "{}.{:04d}.dcc-mcp-{}.partial.exr".format(stem, frame, job_id)
        staged_path.write_bytes("validated frame {}".format(frame).encode("ascii"))
        artifacts.append(
            {
                "frame": frame,
                "staging_path": str(staged_path),
                "final_path": str(final_path),
                "state": "staged",
                "committed": False,
            }
        )
    transaction = {
        "mode": "staged_no_clobber",
        "state": "staged",
        "output_parm_name": "vm_picture",
        "final_output_pattern": str(tmp_path / "{}.$F4.exr".format(stem)),
        "staging_output_pattern": str(tmp_path / "{}.$F4.partial.exr".format(stem)),
        "artifacts": artifacts,
        "aggregate": _render_artifacts.aggregate_artifacts(artifacts),
    }
    job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
    job_dir.mkdir(parents=True)
    status_path = job_dir / "status.json"
    status_path.write_text(
        json.dumps({"job_id": job_id, "state": "completed", "artifact_transaction": transaction}),
        encoding="utf-8",
    )
    return job_id, status_path, artifacts


def _finalize_frame_in_process(tmp_root, job_id, receipt, start_event, result_queue):
    real_identity = _rop_jobs.stable_file_identity
    delayed = [False]

    def delayed_identity(path):
        if not delayed[0] and os.path.normcase(str(path)) == os.path.normcase(receipt["staging_path"]):
            delayed[0] = True
            time.sleep(1.0)
        return real_identity(path)

    start_event.wait(10.0)
    try:
        with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_root)), patch.object(
            _rop_jobs, "stable_file_identity", side_effect=delayed_identity
        ):
            result_queue.put(("ok", _rop_jobs.finalize_render_outputs(job_id, [receipt])))
    except Exception as exc:  # noqa: BLE001
        result_queue.put(("error", type(exc).__name__, str(exc)))


def _block_first_staging_identity(receipt, entered, release):
    real_identity = _rop_jobs.stable_file_identity
    blocked = [False]

    def identity(path):
        if not blocked[0] and os.path.normcase(str(path)) == os.path.normcase(receipt["staging_path"]):
            blocked[0] = True
            entered.set()
            if not release.wait(5.0):
                raise TimeoutError("test did not release slow identity")
        return real_identity(path)

    return identity


def _receipt(job_id: str, artifact: dict) -> dict:
    identity = _render_artifacts.stable_file_identity(artifact["staging_path"])
    return {
        "accepted": True,
        "job_id": job_id,
        "frame": artifact["frame"],
        "staging_path": artifact["staging_path"],
        "final_path": artifact["final_path"],
        **identity,
        "validator": dict(_VALIDATOR),
    }


def test_transaction_request_and_frames_are_fail_closed() -> None:
    assert _render_artifacts.integer_frames([3, 1, -1]) == [3, 2, 1]
    with pytest.raises(ValueError, match="mode"):
        _render_artifacts.normalize_transaction_request({"mode": "replace"})
    with pytest.raises(ValueError, match="integral"):
        _render_artifacts.integer_frames([1, 2.5, 1])


def test_integer_frames_accepts_the_bounded_limit_in_both_directions() -> None:
    limit = _render_artifacts.MAX_TRANSACTION_FRAMES
    assert 1 <= limit <= 100000
    assert len(_render_artifacts.integer_frames([1, limit])) == limit
    assert len(_render_artifacts.integer_frames([limit, 1, -1])) == limit
    assert len(_render_artifacts.integer_frames([1, 1 + ((limit - 1) * 2), 2])) == limit


def test_integer_frames_rejects_above_limit_before_expansion() -> None:
    limit = _render_artifacts.MAX_TRANSACTION_FRAMES
    with patch.object(_render_artifacts, "range", side_effect=AssertionError("range must not expand"), create=True):
        with pytest.raises(ValueError, match="at most"):
            _render_artifacts.integer_frames([1, limit + 1])
        with pytest.raises(ValueError, match="at most"):
            _render_artifacts.integer_frames([1, 10**1000])


def test_windows_status_read_retries_permission_errors(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text(json.dumps({"state": "completed"}), encoding="utf-8")
    real_read_text = Path.read_text
    attempts = [0]

    def flaky_read_text(path, *args, **kwargs):
        attempts[0] += 1
        if attempts[0] < 3:
            raise PermissionError("status reader temporarily blocked")
        return real_read_text(path, *args, **kwargs)

    with patch.object(_status_io.os, "name", "nt"), patch.object(
        _status_io, "_STATUS_IO_POLL_SECONDS", 0.0
    ), patch.object(Path, "read_text", autospec=True, side_effect=flaky_read_text):
        assert _isolated_jobs._read_status(status_path) == {"state": "completed"}
    assert attempts[0] == 3


def test_windows_status_replace_retries_and_preserves_atomic_document(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text(json.dumps({"state": "old"}), encoding="utf-8")
    real_replace = os.replace
    attempts = [0]

    def flaky_replace(source, destination):
        attempts[0] += 1
        if attempts[0] < 3:
            assert json.loads(status_path.read_text(encoding="utf-8")) == {"state": "old"}
            raise PermissionError("status destination temporarily open")
        return real_replace(source, destination)

    with patch.object(_status_io.os, "name", "nt"), patch.object(
        _status_io, "_STATUS_IO_POLL_SECONDS", 0.0
    ), patch.object(_status_io.os, "replace", side_effect=flaky_replace):
        _isolated_jobs.write_status(status_path, {"state": "new"})
    assert attempts[0] == 3
    assert json.loads(status_path.read_text(encoding="utf-8")) == {"state": "new"}
    assert not list(tmp_path.glob("status.json.*.tmp"))


def test_windows_status_replace_timeout_preserves_old_document_and_cleans_pending(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text(json.dumps({"state": "old"}), encoding="utf-8")
    blocked = PermissionError("status destination stayed open")

    with patch.object(_status_io.os, "name", "nt"), patch.object(
        _status_io, "_STATUS_IO_TIMEOUT_SECONDS", 0.0
    ), patch.object(_status_io.os, "replace", side_effect=blocked):
        with pytest.raises(TimeoutError, match="status file") as captured:
            _isolated_jobs.write_status(status_path, {"state": "new"})
    assert captured.value.__cause__ is blocked
    assert json.loads(status_path.read_text(encoding="utf-8")) == {"state": "old"}
    assert not list(tmp_path.glob("status.json.*.tmp"))


def test_status_replace_non_permission_error_is_preserved_and_pending_is_cleaned(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text(json.dumps({"state": "old"}), encoding="utf-8")
    failure = OSError("status disk failure")

    with patch.object(_status_io.os, "name", "nt"), patch.object(_status_io.os, "replace", side_effect=failure):
        with pytest.raises(OSError, match="status disk failure") as captured:
            _isolated_jobs.write_status(status_path, {"state": "new"})
    assert captured.value is failure
    assert json.loads(status_path.read_text(encoding="utf-8")) == {"state": "old"}
    assert not list(tmp_path.glob("status.json.*.tmp"))


@pytest.mark.parametrize(
    ("platform_name", "error"),
    [("posix", PermissionError("permission denied")), ("nt", OSError("disk failure"))],
)
def test_status_io_does_not_retry_out_of_scope_errors(platform_name: str, error: OSError) -> None:
    operation = MagicMock(side_effect=error)
    with patch.object(_status_io.os, "name", platform_name):
        with pytest.raises(type(error), match=str(error)):
            _status_io._retry_windows_status_io(operation, "testing status file")
    operation.assert_called_once_with()


def test_job_transaction_lock_releases_after_exception(tmp_path: Path) -> None:
    status_path = tmp_path / "job" / "status.json"
    status_path.parent.mkdir()
    with pytest.raises(RuntimeError, match="inside lock"):
        with _rop_jobs._artifact_transaction_lock(status_path):
            raise RuntimeError("inside lock")
    with _rop_jobs._artifact_transaction_lock(status_path):
        pass


def test_job_transaction_lock_times_out_and_remains_available(tmp_path: Path) -> None:
    status_path = tmp_path / "job" / "status.json"
    status_path.parent.mkdir()
    with patch.object(_rop_jobs, "_ARTIFACT_LOCK_TIMEOUT_SECONDS", 0.0), patch.object(
        _rop_jobs, "_try_artifact_transaction_lock", return_value=False
    ):
        with pytest.raises(TimeoutError, match="artifact transaction lock"):
            with _rop_jobs._artifact_transaction_lock(status_path):
                pass
    with _rop_jobs._artifact_transaction_lock(status_path):
        pass


def test_slow_finalize_does_not_block_other_job_read_or_cancel(tmp_path: Path) -> None:
    job_a, _, artifacts_a = _completed_job(tmp_path, job_id="2" * 32, stem="job_a")
    job_b, _, _ = _completed_job(tmp_path, job_id="3" * 32, stem="job_b")
    receipt = _receipt(job_a, artifacts_a[0])
    entered = threading.Event()
    release = threading.Event()
    slow_identity = _block_first_staging_identity(receipt, entered, release)

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
        _rop_jobs, "stable_file_identity", side_effect=slow_identity
    ), ThreadPoolExecutor(max_workers=3) as pool:
        finalize_future = pool.submit(_rop_jobs.finalize_render_outputs, job_a, [receipt])
        try:
            assert entered.wait(5.0)
            read_future = pool.submit(_rop_jobs.read_render_job, job_b)
            cancel_future = pool.submit(_rop_jobs.cancel_render_job, job_b)
            _, blocked = wait([read_future, cancel_future], timeout=1.0)
        finally:
            release.set()
        finalize_future.result(timeout=5.0)
        assert not blocked
        assert read_future.result(timeout=1.0)["job_id"] == job_b
        assert cancel_future.result(timeout=1.0)["cancel_requested"] is False


def test_second_same_job_finalizer_observes_file_lock_timeout(tmp_path: Path) -> None:
    job_id, _, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    entered = threading.Event()
    release = threading.Event()
    slow_identity = _block_first_staging_identity(receipt, entered, release)

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
        _rop_jobs, "_ARTIFACT_LOCK_TIMEOUT_SECONDS", 0.2
    ), patch.object(_rop_jobs, "stable_file_identity", side_effect=slow_identity), ThreadPoolExecutor(
        max_workers=2
    ) as pool:
        first = pool.submit(_rop_jobs.finalize_render_outputs, job_id, [receipt])
        try:
            assert entered.wait(5.0)
            second = pool.submit(_rop_jobs.finalize_render_outputs, job_id, [receipt])
            _, blocked = wait([second], timeout=1.0)
        finally:
            release.set()
        first.result(timeout=5.0)
        assert not blocked
        with pytest.raises(TimeoutError, match="artifact transaction lock"):
            second.result(timeout=1.0)


def test_finalize_and_high_frequency_poll_share_atomic_status_file(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path, count=20)
    receipts = [_receipt(job_id, artifact) for artifact in artifacts]
    poller_count = 4
    start = threading.Barrier(poller_count + 1)
    stop = threading.Event()
    poll_errors = []
    poll_count = [0]

    def poll_status():
        start.wait(timeout=5.0)
        while not stop.is_set():
            try:
                result = _rop_jobs.read_render_job(job_id, include_details=True)
                transaction = result["artifact_transaction"]
                assert len(transaction["artifacts"]) == 20
                assert len({artifact["frame"] for artifact in transaction["artifacts"]}) == 20
                assert transaction["aggregate"]["total"] == 20
                poll_count[0] += 1
            except Exception as exc:  # noqa: BLE001
                poll_errors.append(exc)
                stop.set()

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), ThreadPoolExecutor(
        max_workers=poller_count
    ) as pool:
        pollers = [pool.submit(poll_status) for _ in range(poller_count)]
        start.wait(timeout=5.0)
        try:
            finalized = _rop_jobs.finalize_render_outputs(job_id, receipts)
        finally:
            stop.set()
            for poller in pollers:
                poller.result(timeout=5.0)

    assert not poll_errors
    assert poll_count[0] > 0
    assert finalized["aggregate"]["complete"] is True
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["artifact_transaction"]["aggregate"]["complete"] is True
    assert {artifact["state"] for artifact in status["artifact_transaction"]["artifacts"]} == {"committed"}


def test_worker_status_writes_survive_four_high_frequency_adapter_pollers(tmp_path: Path) -> None:
    worker = _load_script("_render_worker.py")
    status_path = tmp_path / "status.json"
    artifacts = [
        {
            "frame": frame,
            "state": "rendering",
            "staging_path": str(tmp_path / "beauty.{:04d}.partial.exr".format(frame)),
            "final_path": str(tmp_path / "beauty.{:04d}.exr".format(frame)),
        }
        for frame in range(1, 21)
    ]
    payload = {"state": "running", "sequence": -1, "artifact_transaction": {"artifacts": artifacts}}
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    poller_count = 4
    rounds = 10
    opened = [threading.Event() for _ in range(rounds)]
    release = [threading.Event() for _ in range(rounds)]
    opened_counts = [0] * rounds
    counter_lock = threading.Lock()
    poller_round = threading.local()
    read_errors = []
    write_errors = []
    completed_while_readers_held = []
    real_read_text = Path.read_text

    def hold_status_read(path, *args, **kwargs):
        round_index = getattr(poller_round, "index", None)
        if round_index is None or Path(path) != status_path:
            return real_read_text(path, *args, **kwargs)
        with Path(path).open(
            mode="r",
            encoding=kwargs.get("encoding"),
            errors=kwargs.get("errors"),
        ) as stream:
            document = stream.read()
            with counter_lock:
                opened_counts[round_index] += 1
                if opened_counts[round_index] == poller_count:
                    opened[round_index].set()
            assert release[round_index].wait(timeout=5.0)
            return document

    def poll_once(round_index):
        poller_round.index = round_index
        try:
            observed = _isolated_jobs._read_status(status_path)
            assert isinstance(observed["sequence"], int)
            assert len(observed["artifact_transaction"]["artifacts"]) == 20
        except Exception as exc:  # noqa: BLE001
            read_errors.append(exc)
        finally:
            del poller_round.index

    with patch.object(Path, "read_text", autospec=True, side_effect=hold_status_read), ThreadPoolExecutor(
        max_workers=poller_count + 1
    ) as pool:
        for sequence in range(rounds):
            pollers = [pool.submit(poll_once, sequence) for _ in range(poller_count)]
            assert opened[sequence].wait(timeout=5.0)
            next_payload = dict(payload)
            next_payload["sequence"] = sequence
            writer = pool.submit(worker.write_status, status_path, next_payload)
            time.sleep(0.02)
            completed_while_readers_held.append(writer.done())
            release[sequence].set()
            for poller in pollers:
                poller.result(timeout=5.0)
            try:
                writer.result(timeout=5.0)
            except PermissionError as exc:
                write_errors.append(exc)

    pending = list(tmp_path.glob("status.json.*.tmp"))
    assert not read_errors
    assert not write_errors, {
        "write_error_count": len(write_errors),
        "pending_status_files": [path.name for path in pending],
    }
    if os.name == "nt":
        assert completed_while_readers_held == [False] * rounds
    assert _isolated_jobs._read_status(status_path)["sequence"] == rounds - 1
    assert not pending


def test_worker_retries_transient_initial_status_write_before_render_try(tmp_path: Path) -> None:
    real_replace = os.replace
    attempts = [0]

    def transient_replace(source, destination):
        attempts[0] += 1
        if attempts[0] == 1:
            raise PermissionError("initial worker status destination temporarily open")
        return real_replace(source, destination)

    status_os = SimpleNamespace(name="nt", replace=MagicMock(side_effect=transient_replace))
    with patch.object(_status_io, "os", status_os):
        status, _, _, _ = _run_transaction_worker(tmp_path)

    assert status["state"] == "completed"
    assert attempts[0] >= 2
    assert not list(tmp_path.glob("status.json.*.tmp"))


def test_get_render_settings_prefers_outputimage_and_reports_exact_parm() -> None:
    module = _load_script("get_render_settings.py")
    outputimage = MagicMock()
    outputimage.unexpandedString.return_value = "/tmp/beauty.$F4.exr"
    outputimage.eval.return_value = "/tmp/beauty.0001.exr"
    lopoutput = MagicMock()
    lopoutput.unexpandedString.return_value = "/tmp/render.usd"
    lopoutput.eval.return_value = "/tmp/render.usd"
    rop = MagicMock()
    rop.parm.side_effect = lambda name: {"outputimage": outputimage, "lopoutput": lopoutput}.get(name)
    rop.parmTuple.return_value = None
    rop.path.return_value = "/stage/karma"
    rop.name.return_value = "karma"
    rop.type.return_value.name.return_value = "usdrender_rop"
    mock_hou = MagicMock()
    mock_hou.node.return_value = rop
    mock_hou.frame.return_value = 1.0
    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = module.get_render_settings("/stage/karma")["context"]
    assert result["output_parm_name"] == "outputimage"
    assert result["output_path_pattern"] == "/tmp/beauty.$F4.exr"


def test_render_rop_opts_in_only_for_background(tmp_path: Path) -> None:
    module = _load_script("render_rop.py")
    output = MagicMock()
    output.unexpandedString.return_value = str(tmp_path / "beauty.$F4.exr")
    rop = MagicMock()
    rop.parm.side_effect = lambda name: output if name == "vm_picture" else None
    rop.parmTuple.return_value = None
    rop.path.return_value = "/out/mantra1"
    rop.name.return_value = "mantra1"
    rop.type.return_value.name.return_value = "ifd"
    mock_hou = MagicMock()
    mock_hou.node.return_value = rop
    request = {"mode": "staged_no_clobber"}
    with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(
        module,
        "launch_background_render",
        return_value={"job_id": "f" * 32, "state": "queued"},
    ) as launch:
        background = module.render_rop(
            "/out/mantra1", frame_range=[1, 1, 1], background=True, artifact_transaction=request
        )
        foreground = module.render_rop(
            "/out/mantra1", frame_range=[1, 1, 1], background=False, artifact_transaction=request
        )
    assert background["success"] is True
    launch.assert_called_once_with(
        mock_hou,
        "/out/mantra1",
        [1, 1, 1],
        str(tmp_path / "beauty.$F4.exr"),
        artifact_transaction=request,
    )
    assert foreground["success"] is False
    rop.render.assert_not_called()


def test_background_launch_persists_transaction_without_changing_worker_argv(tmp_path: Path) -> None:
    module = _load_script("_background_render.py")
    hip = tmp_path / "scene.hip"
    hip.write_bytes(b"hip")
    hython = tmp_path / ("hython.exe" if module.os.name == "nt" else "hython")
    hython.write_bytes(b"exe")
    mock_hou = MagicMock()
    mock_hou.hipFile.path.return_value = str(hip)
    mock_hou.hipFile.hasUnsavedChanges.return_value = False
    mock_hou.isUIAvailable.return_value = True
    process = MagicMock(pid=4321)
    request = {"mode": "staged_no_clobber"}
    with patch.object(module.sys, "executable", str(tmp_path / "houdini.exe")), patch.object(
        module.tempfile, "gettempdir", return_value=str(tmp_path)
    ), patch.object(module.subprocess, "Popen", return_value=process) as popen:
        job = module.launch_background_render(
            mock_hou,
            "/out/mantra1",
            [1, 2, 1],
            str(tmp_path / "beauty.$F4.exr"),
            artifact_transaction=request,
        )
    status_path = tmp_path / "dcc-mcp-houdini-render-jobs" / job["job_id"] / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["artifact_transaction"]["state"] == "queued"
    assert status["artifact_transaction"]["requested_frames"] == [1, 2]
    command = popen.call_args.args[0]
    assert len(command) == 8
    assert json.loads(command[4]) == [1, 2, 1]
    module._PROCESS_HANDLES.pop(job["job_id"], None)


def test_worker_stages_in_memory_without_saving_or_writing_final(tmp_path: Path) -> None:
    status, parms, mock_hou, final_pattern = _run_transaction_worker(tmp_path)
    transaction = status["artifact_transaction"]
    assert status["state"] == "completed"
    assert transaction["state"] == "staged"
    assert transaction["output_parm_name"] == "vm_picture"
    assert transaction["aggregate"]["staged"] == 2
    assert parms["vm_picture"].set_calls[0].endswith(".partial.exr")
    assert parms["vm_picture"].set_calls[-1] == final_pattern
    assert not list(tmp_path.glob("beauty.000?.exr"))
    assert len(list(tmp_path.glob("*.partial.exr"))) == 2
    mock_hou.hipFile.save.assert_not_called()


def test_worker_rejects_multiple_primary_exr_outputs(tmp_path: Path) -> None:
    status, _, _, _ = _run_transaction_worker(
        tmp_path,
        outputs={
            "vm_picture": str(tmp_path / "beauty.$F4.exr"),
            "outputimage": str(tmp_path / "second.$F4.exr"),
        },
    )
    assert status["state"] == "failed"
    assert status["artifact_transaction"]["state"] == "render_failed"
    assert "exactly one" in status["error"]


def test_worker_rejects_rop_input_chains(tmp_path: Path) -> None:
    status, _, _, _ = _run_transaction_worker(tmp_path, rop_inputs=(object(),))
    assert status["state"] == "failed"
    assert status["artifact_transaction"]["state"] == "render_failed"
    assert "input chains" in status["error"]
    assert not list(tmp_path.glob("*.partial.exr"))


@pytest.mark.parametrize("render_error", [None, "renderer crashed"])
def test_worker_partial_or_error_never_publishes_final(tmp_path: Path, render_error: str) -> None:
    status, _, _, _ = _run_transaction_worker(tmp_path, produced=(1,), render_error=render_error)
    assert status["state"] == "failed"
    assert status["artifact_transaction"]["state"] == "render_failed"
    assert status["artifact_transaction"]["aggregate"]["failed"] == 2
    assert not list(tmp_path.glob("beauty.000?.exr"))


def test_cancel_updates_worker_and_transaction_states() -> None:
    status = {
        "state": "cancelling",
        "artifact_transaction": {
            "mode": "staged_no_clobber",
            "state": "rendering",
            "artifacts": [{"frame": 1, "state": "rendering", "committed": False}],
        },
    }
    result = _isolated_jobs._finish_status(status, "cancelled", -1)
    assert result["state"] == "cancelled"
    assert result["artifact_transaction"]["state"] == "cancelled"
    assert result["artifact_transaction"]["artifacts"][0]["state"] == "cancelled"


def test_posix_publication_is_no_clobber_and_unlinks_stage(tmp_path: Path) -> None:
    staged = tmp_path / "stage.exr"
    final = tmp_path / "final.exr"
    staged.write_bytes(b"first")
    result = _render_artifacts.publish_no_clobber(staged, final, platform_name="posix")
    assert result == {"committed": True, "cleanup_error": None}
    assert final.read_bytes() == b"first"
    assert not staged.exists()
    replacement = tmp_path / "replacement.exr"
    replacement.write_bytes(b"second")
    with pytest.raises(FileExistsError):
        _render_artifacts.publish_no_clobber(replacement, final, platform_name="posix")
    assert final.read_bytes() == b"first"


def test_concurrent_posix_publication_has_exactly_one_winner(tmp_path: Path) -> None:
    final = tmp_path / "final.exr"
    staged = [tmp_path / "a.exr", tmp_path / "b.exr"]
    staged[0].write_bytes(b"a")
    staged[1].write_bytes(b"b")

    def publish(path: Path):
        try:
            _render_artifacts.publish_no_clobber(path, final, platform_name="posix")
            return "committed"
        except FileExistsError:
            return "collision"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(publish, staged))
    assert sorted(outcomes) == ["collision", "committed"]
    assert final.read_bytes() in {b"a", b"b"}


def test_windows_path_uses_rename_and_preserves_collision(tmp_path: Path) -> None:
    staged = tmp_path / "stage.exr"
    final = tmp_path / "final.exr"
    staged.write_bytes(b"stage")
    with patch.object(_render_artifacts.os, "rename", wraps=os.rename) as rename:
        _render_artifacts.publish_no_clobber(staged, final, platform_name="nt")
    rename.assert_called_once_with(str(staged), str(final))
    collision = tmp_path / "collision.exr"
    collision.write_bytes(b"new")
    with pytest.raises(FileExistsError):
        _render_artifacts.publish_no_clobber(collision, final, platform_name="nt")
    assert final.read_bytes() == b"stage"


@pytest.mark.parametrize(
    ("platform_name", "primitive_name"),
    [("nt", "rename"), ("posix", "link")],
)
def test_publication_preserves_ambiguous_final_when_source_changes_after_identity_check(
    tmp_path: Path,
    platform_name: str,
    primitive_name: str,
) -> None:
    staged = tmp_path / "stage.exr"
    final = tmp_path / "final.exr"
    staged.write_bytes(b"validated bytes")
    expected_identity = _render_artifacts.stable_file_identity(staged)
    real_primitive = getattr(os, primitive_name)

    def replace_then_publish(source, destination, *args, **kwargs):
        staged.unlink()
        staged.write_bytes(b"unvalidated replacement")
        return real_primitive(source, destination, *args, **kwargs)

    with patch.object(_render_artifacts.os, primitive_name, side_effect=replace_then_publish):
        with pytest.raises(ValueError, match="identity"):
            _render_artifacts.publish_no_clobber(
                staged,
                final,
                platform_name=platform_name,
                expected_identity=expected_identity,
            )
    assert final.read_bytes() == b"unvalidated replacement"


@pytest.mark.parametrize(
    ("platform_name", "primitive_name"),
    [("nt", "rename"), ("posix", "link")],
)
def test_publication_identity_mismatch_never_deletes_unowned_final(
    tmp_path: Path,
    platform_name: str,
    primitive_name: str,
) -> None:
    staged = tmp_path / "stage.exr"
    final = tmp_path / "final.exr"
    staged.write_bytes(b"validated frame")
    expected_identity = _render_artifacts.stable_file_identity(staged)
    unrelated_bytes = b"artist replacement after publication"
    unrelated_sha256 = hashlib.sha256(unrelated_bytes).hexdigest()
    real_primitive = getattr(os, primitive_name)

    def publish_then_replace(source, destination, *args, **kwargs):
        result = real_primitive(source, destination, *args, **kwargs)
        final.unlink()
        final.write_bytes(unrelated_bytes)
        return result

    with patch.object(_render_artifacts.os, primitive_name, side_effect=publish_then_replace):
        with pytest.raises(ValueError, match="identity"):
            _render_artifacts.publish_no_clobber(
                staged,
                final,
                platform_name=platform_name,
                expected_identity=expected_identity,
            )

    assert final.read_bytes() == unrelated_bytes
    assert _render_artifacts.stable_file_identity(final)["sha256"] == unrelated_sha256


@pytest.mark.parametrize(
    ("platform_name", "primitive_name"),
    [("nt", "rename"), ("posix", "link")],
)
@pytest.mark.parametrize(
    "validation_error",
    [
        FileNotFoundError("published final disappeared before validation"),
        ValueError("published final became non-regular"),
        OSError("published final validation unavailable"),
    ],
)
def test_post_publication_validation_exception_reports_ambiguous_ownership(
    tmp_path: Path,
    platform_name: str,
    primitive_name: str,
    validation_error: Exception,
) -> None:
    staged = tmp_path / "stage.exr"
    final = tmp_path / "final.exr"
    staged.write_bytes(b"validated frame")
    expected_identity = _render_artifacts.stable_file_identity(staged)
    real_identity = _render_artifacts.stable_file_identity

    def fail_final_validation(path):
        if os.path.normcase(str(path)) == os.path.normcase(str(final)):
            raise validation_error
        return real_identity(path)

    with patch.object(_render_artifacts, "stable_file_identity", side_effect=fail_final_validation):
        with pytest.raises(_render_artifacts.PublicationIdentityMismatchError) as captured:
            _render_artifacts.publish_no_clobber(
                staged,
                final,
                platform_name=platform_name,
                expected_identity=expected_identity,
            )

    assert captured.value.__cause__ is validation_error
    assert final.read_bytes() == b"validated frame"


@pytest.mark.parametrize(
    ("platform_name", "primitive_name"),
    [("nt", "rename"), ("posix", "link")],
)
def test_post_publication_nonregular_replacement_is_never_removed(
    tmp_path: Path,
    platform_name: str,
    primitive_name: str,
) -> None:
    staged = tmp_path / "stage.exr"
    final = tmp_path / "final.exr"
    staged.write_bytes(b"validated frame")
    expected_identity = _render_artifacts.stable_file_identity(staged)
    real_primitive = getattr(os, primitive_name)

    def publish_then_replace_with_directory(source, destination, *args, **kwargs):
        result = real_primitive(source, destination, *args, **kwargs)
        final.unlink()
        final.mkdir()
        return result

    with patch.object(
        _render_artifacts.os,
        primitive_name,
        side_effect=publish_then_replace_with_directory,
    ):
        with pytest.raises(_render_artifacts.PublicationIdentityMismatchError) as captured:
            _render_artifacts.publish_no_clobber(
                staged,
                final,
                platform_name=platform_name,
                expected_identity=expected_identity,
            )

    assert isinstance(captured.value.__cause__, ValueError)
    assert final.is_dir()


def test_finalize_persists_ambiguous_publication_as_attention_required(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    final = Path(artifacts[0]["final_path"])
    unrelated_bytes = b"unowned replacement after publication"
    unrelated_sha256 = hashlib.sha256(unrelated_bytes).hexdigest()
    primitive_name = "rename" if os.name == "nt" else "link"
    real_primitive = getattr(os, primitive_name)

    def publish_then_replace(source, destination, *args, **kwargs):
        result = real_primitive(source, destination, *args, **kwargs)
        final.unlink()
        final.write_bytes(unrelated_bytes)
        return result

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
        _render_artifacts.os, primitive_name, side_effect=publish_then_replace
    ):
        with pytest.raises(ValueError, match="identity"):
            _rop_jobs.finalize_render_outputs(job_id, [receipt])

    assert final.read_bytes() == unrelated_bytes
    assert _render_artifacts.stable_file_identity(final)["sha256"] == unrelated_sha256
    status = json.loads(status_path.read_text(encoding="utf-8"))
    transaction = status["artifact_transaction"]
    artifact = transaction["artifacts"][0]
    assert artifact["state"] == "attention_required"
    assert artifact["committed"] is True
    assert transaction["aggregate"]["state"] == "blocked"


def test_cross_volume_identity_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    staged = tmp_path / "stage.exr"
    final = tmp_path / "final.exr"
    staged.write_bytes(b"stage")
    real_lstat = _render_artifacts.os.lstat

    def lstat(path):
        result = real_lstat(path)
        if os.path.normcase(str(path)) == os.path.normcase(str(staged)):
            return SimpleNamespace(
                st_dev=result.st_dev + 1,
                st_ino=result.st_ino,
                st_mode=result.st_mode,
                st_size=result.st_size,
                st_mtime_ns=result.st_mtime_ns,
                st_file_attributes=0,
            )
        return result

    monkeypatch.setattr(_render_artifacts.os, "lstat", lstat)
    with pytest.raises(ValueError, match="same volume"):
        _render_artifacts.assert_same_parent_and_volume(staged, final)


def test_windows_reparse_output_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "stage.exr"
    output.write_bytes(b"stage")
    real_lstat = _render_artifacts.os.lstat

    def lstat(path):
        result = real_lstat(path)
        if os.path.normcase(str(path)) == os.path.normcase(str(output)):
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
        return result

    monkeypatch.setattr(_render_artifacts.os, "lstat", lstat)
    with pytest.raises(ValueError, match="reparse"):
        _render_artifacts.assert_no_links_or_reparse(output)


def test_finalize_binds_receipt_and_updates_aggregate(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        first = _rop_jobs.finalize_render_outputs(job_id, [receipt])
        repeated = _rop_jobs.finalize_render_outputs(job_id, [receipt])
    assert first["aggregate"]["complete"] is True
    assert repeated["finalized_frames"] == [1]
    status = json.loads(status_path.read_text(encoding="utf-8"))
    artifact = status["artifact_transaction"]["artifacts"][0]
    assert artifact["committed"] is True
    assert artifact["state"] == "committed"
    assert artifact["validator_receipt"] == receipt
    assert Path(artifact["final_path"]).read_bytes() == b"validated frame 1"


def test_finalize_rejects_staged_drift_without_writing_final(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    Path(artifacts[0]["staging_path"]).write_bytes(b"changed after validation")
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        with pytest.raises(ValueError, match="receipt"):
            _rop_jobs.finalize_render_outputs(job_id, [receipt])
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["artifact_transaction"]["artifacts"][0]["state"] == "drifted"
    assert not Path(artifacts[0]["final_path"]).exists()


def test_finalize_rejects_drift_after_persisting_publish_intent_without_writing_final(tmp_path: Path) -> None:
    job_id, _, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    real_write_status = _isolated_jobs.write_status

    def write_status(path, payload):
        real_write_status(path, payload)
        transaction = payload.get("artifact_transaction", {})
        if any(artifact.get("state") == "publishing" for artifact in transaction.get("artifacts", [])):
            Path(artifacts[0]["staging_path"]).write_bytes(b"changed after publication intent")

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
        _isolated_jobs, "write_status", side_effect=write_status
    ):
        with pytest.raises(ValueError, match="identity"):
            _rop_jobs.finalize_render_outputs(job_id, [receipt])
    assert not Path(artifacts[0]["final_path"]).exists()


def test_finalize_collision_never_overwrites_final(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    final = Path(artifacts[0]["final_path"])
    final.write_bytes(b"artist-owned")
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        with pytest.raises(FileExistsError):
            _rop_jobs.finalize_render_outputs(job_id, [receipt])
    assert final.read_bytes() == b"artist-owned"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["artifact_transaction"]["artifacts"][0]["state"] == "collision"


def test_finalize_preserves_committed_evidence_when_post_check_fails(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    real_identity = _rop_jobs.stable_file_identity

    def identity(path):
        if os.path.normcase(str(path)) == os.path.normcase(artifacts[0]["final_path"]):
            raise OSError("post-commit verification unavailable")
        return real_identity(path)

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
        _rop_jobs, "stable_file_identity", side_effect=identity
    ):
        with pytest.raises(OSError, match="post-commit"):
            _rop_jobs.finalize_render_outputs(job_id, [receipt])
    status = json.loads(status_path.read_text(encoding="utf-8"))
    artifact = status["artifact_transaction"]["artifacts"][0]
    assert artifact["committed"] is True
    assert artifact["state"] == "commit_verification_failed"
    assert Path(artifact["final_path"]).is_file()


def test_finalize_retry_recovers_transient_post_commit_failure(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
        _rop_jobs, "fsync_parent", side_effect=OSError("transient flush failure")
    ):
        with pytest.raises(OSError, match="transient flush failure"):
            _rop_jobs.finalize_render_outputs(job_id, [receipt])

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        recovered = _rop_jobs.finalize_render_outputs(job_id, [receipt])

    assert recovered["transaction_state"] == "committed"
    assert recovered["aggregate"]["complete"] is True
    status = json.loads(status_path.read_text(encoding="utf-8"))
    artifact = status["artifact_transaction"]["artifacts"][0]
    assert artifact["state"] == "committed"
    assert "post_commit_error" not in artifact


def test_finalize_retry_recovers_transient_helper_post_check_failure(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    real_identity = _render_artifacts.stable_file_identity
    failed = [False]

    def transient_final_identity(path):
        if not failed[0] and os.path.normcase(str(path)) == os.path.normcase(artifacts[0]["final_path"]):
            failed[0] = True
            raise OSError("transient helper post-check failure")
        return real_identity(path)

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
        _render_artifacts, "stable_file_identity", side_effect=transient_final_identity
    ):
        with pytest.raises(_render_artifacts.PublicationIdentityMismatchError) as captured:
            _rop_jobs.finalize_render_outputs(job_id, [receipt])
    assert isinstance(captured.value.__cause__, OSError)
    assert "transient helper post-check failure" in str(captured.value.__cause__)
    assert Path(artifacts[0]["final_path"]).is_file()
    failed_status = json.loads(status_path.read_text(encoding="utf-8"))
    failed_artifact = failed_status["artifact_transaction"]["artifacts"][0]
    assert failed_artifact["state"] == "attention_required"
    assert failed_artifact["committed"] is True
    assert failed_status["artifact_transaction"]["aggregate"]["state"] == "blocked"

    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        recovered = _rop_jobs.finalize_render_outputs(job_id, [receipt])

    assert recovered["transaction_state"] == "committed"
    assert recovered["aggregate"]["complete"] is True
    status = json.loads(status_path.read_text(encoding="utf-8"))
    artifact = status["artifact_transaction"]["artifacts"][0]
    assert artifact["state"] == "committed"
    assert "last_error" not in artifact


def test_two_processes_finalize_different_frames_without_lost_status(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path, count=2)
    receipts = [_receipt(job_id, artifact) for artifact in artifacts]
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_finalize_frame_in_process,
            args=(tmp_path, job_id, receipt, start_event, result_queue),
        )
        for receipt in receipts
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(20.0)
    hung = [process for process in processes if process.is_alive()]
    for process in hung:
        process.terminate()
        process.join(5.0)
    assert not hung
    assert [process.exitcode for process in processes] == [0, 0]
    results = [result_queue.get(timeout=5.0) for _ in processes]
    result_queue.close()
    result_queue.join_thread()
    assert [result[0] for result in results] == ["ok", "ok"]

    status = json.loads(status_path.read_text(encoding="utf-8"))
    transaction = status["artifact_transaction"]
    assert [artifact["state"] for artifact in transaction["artifacts"]] == ["committed", "committed"]
    assert transaction["aggregate"]["complete"] is True
    assert all(Path(artifact["final_path"]).is_file() for artifact in transaction["artifacts"])


def test_finalize_recovers_commit_before_status_update(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path)
    receipt = _receipt(job_id, artifacts[0])
    status = json.loads(status_path.read_text(encoding="utf-8"))
    artifact = status["artifact_transaction"]["artifacts"][0]
    artifact.update({"state": "publishing", "validator_receipt": receipt})
    os.rename(artifact["staging_path"], artifact["final_path"])
    status_path.write_text(json.dumps(status), encoding="utf-8")
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        result = _rop_jobs.finalize_render_outputs(job_id, [receipt])
    assert result["aggregate"]["complete"] is True
    recovered = json.loads(status_path.read_text(encoding="utf-8"))["artifact_transaction"]["artifacts"][0]
    assert recovered["committed"] is True
    assert recovered["state"] == "committed"
    assert "recovered_at" in recovered


def test_aggregate_revalidates_previous_final_before_next_commit(tmp_path: Path) -> None:
    job_id, status_path, artifacts = _completed_job(tmp_path, count=2)
    first_receipt = _receipt(job_id, artifacts[0])
    second_receipt = _receipt(job_id, artifacts[1])
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        _rop_jobs.finalize_render_outputs(job_id, [first_receipt])
        Path(artifacts[0]["final_path"]).write_bytes(b"drifted final")
        with pytest.raises(ValueError, match="drifted"):
            _rop_jobs.finalize_render_outputs(job_id, [second_receipt])
    assert not Path(artifacts[1]["final_path"]).exists()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["artifact_transaction"]["aggregate"]["state"] == "blocked"


def test_get_render_job_bounds_transaction_details(tmp_path: Path) -> None:
    job_id, _, artifacts = _completed_job(tmp_path)
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        summary = _rop_jobs.read_render_job(job_id)
        details = _rop_jobs.read_render_job(job_id, include_details=True)
    assert "artifacts" not in summary["artifact_transaction"]
    assert summary["artifact_transaction"]["aggregate"]["total"] == 1
    assert details["artifact_transaction"]["artifacts"][0]["frame"] == artifacts[0]["frame"]
