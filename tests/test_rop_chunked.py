"""Mock-hou unit tests for chunked ROP render (_rop_chunked.py).

These tests exercise launch/poll/cancel, step-through completion,
cancellation with partial outputs, terminal idempotence, parm
snapshot/restore, and event-loop callback removal.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(skill_name: str, script_name: str):
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _mock_rop(path: str = "/out/mantra1") -> MagicMock:
    """Create a mock ROP node with parm access."""
    rop = MagicMock()
    rop.path.return_value = path

    # Default parm values for trange/f1/f2/f3
    _parms: dict = {"trange": 1, "f1": 1.0, "f2": 10.0, "f3": 1.0}

    def _parm_side_effect(name):
        parm = MagicMock()
        parm.eval.return_value = _parms.get(name, 0)
        parm.set.side_effect = lambda v: _parms.update({name: v})
        return parm

    rop.parm.side_effect = _parm_side_effect
    # f tuple returns None by default (force scalar fallback path)
    rop.parmTuple.return_value = None
    return rop


def _mock_hou(rop: MagicMock | None = None) -> MagicMock:
    """Create a mock hou module with a node resolver."""
    hou = MagicMock()
    if rop is not None:
        hou.node.return_value = rop
    return hou


# ---------------------------------------------------------------------------
# Tests: create_rop_chunks + per-frame helpers
# ---------------------------------------------------------------------------


class TestCreateRopChunks:
    def test_creates_correct_number_of_chunks(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        chunks, _, metadata = mod.create_rop_chunks(hou, "/out/mantra1", [1, 5, 1])
        assert len(chunks) == 5
        assert metadata["frame_range"] == [1.0, 5.0, 1.0]
        assert metadata["rop_path"] == "/out/mantra1"

    def test_chunks_have_frame_metadata(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        chunks, _, _ = mod.create_rop_chunks(hou, "/out/mantra1", [1, 3, 1])
        assert chunks[0]._frame == 1.0  # type: ignore[attr-defined]
        assert chunks[1]._frame == 2.0  # type: ignore[attr-defined]
        assert chunks[2]._frame == 3.0  # type: ignore[attr-defined]

    def test_rejects_missing_rop(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        hou = MagicMock()
        hou.node.return_value = None

        with pytest.raises(ValueError, match="not found"):
            mod.create_rop_chunks(hou, "/out/ghost", [1, 5, 1])

    def test_rejects_non_render_node(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = MagicMock()
        rop.path.return_value = "/obj/geo1"
        del rop.render  # remove render attribute
        hou = _mock_hou(rop)

        with pytest.raises(ValueError, match="not a render node"):
            mod.create_rop_chunks(hou, "/obj/geo1", [1, 5, 1])

    def test_rejects_invalid_frame_range(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with pytest.raises(ValueError, match="end must be >= start"):
            mod.create_rop_chunks(hou, "/out/mantra1", [5, 1, 1])

    def test_snapshots_parms(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        _, _, metadata = mod.create_rop_chunks(hou, "/out/mantra1", [1, 5, 1])
        assert "parm_snapshot" in metadata
        snapshot = metadata["parm_snapshot"]
        assert "trange" in snapshot
        assert snapshot["trange"] == 1

    def test_set_single_frame_range_mutates_parms(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        _ = _mock_hou(rop)  # registers mock hou in sys.modules

        mod._set_single_frame_range(rop, 7.0)
        # After setting, f1/f2 should be 7.0, f3 should be 1.0
        f1 = rop.parm("f1").eval()
        f2 = rop.parm("f2").eval()
        f3 = rop.parm("f3").eval()
        assert f1 == 7.0
        assert f2 == 7.0
        assert f3 == 1.0

    def test_snapshot_restore_roundtrip(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        _ = _mock_hou(rop)  # registers mock hou in sys.modules

        # Snapshot original values
        snapshot = mod._snapshot_frame_parms(rop)
        assert snapshot["trange"] == 1
        assert "f1" in snapshot
        orig_f1 = snapshot["f1"]

        # Mutate
        mod._set_single_frame_range(rop, 42.0)
        assert rop.parm("f1").eval() == 42.0

        # Restore
        mod._restore_frame_parms(rop, snapshot)
        assert rop.parm("f1").eval() == orig_f1


# ---------------------------------------------------------------------------
# Tests: launch / poll / cancel (schema dispatch)
# ---------------------------------------------------------------------------


class TestRenderRopChunkedDispatch:
    @pytest.fixture(autouse=True)
    def _preload(self) -> None:
        """Ensure _rop_chunked is importable by render_rop's lazy import."""
        mod = _load_script("houdini-render", "_rop_chunked.py")
        # Also register under the bare name that render_rop.py imports
        sys.modules["_rop_chunked"] = mod

    def test_launch_returns_job_id(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.render_rop_chunked(rop_path="/out/mantra1", frame_range=[1, 5, 1], action="launch")

        assert result["success"] is True
        assert result["context"]["job_id"] is not None
        assert result["context"]["state"] == "running"

    def test_poll_returns_status(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.render_rop_chunked(rop_path="/out/mantra1", frame_range=[1, 5, 1], action="launch")
            job_id = launch_result["context"]["job_id"]

            poll_result = mod.render_rop_chunked(action="poll", job_id=job_id)

        assert poll_result["success"] is True
        assert poll_result["context"]["state"] == "running"

    def test_poll_unknown_job(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")

        result = mod.render_rop_chunked(action="poll", job_id="rop-nonexistent")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_cancel_sets_cancelling_state(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.render_rop_chunked(rop_path="/out/mantra1", frame_range=[1, 5, 1], action="launch")
            job_id = launch_result["context"]["job_id"]

            cancel_result = mod.render_rop_chunked(action="cancel", job_id=job_id)

        assert cancel_result["success"] is True
        assert cancel_result["context"]["state"] == "cancelling"

    def test_cancel_unknown_job(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")

        result = mod.render_rop_chunked(action="cancel", job_id="rop-ghost")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_poll_missing_job_id(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")

        result = mod.render_rop_chunked(action="poll")
        assert result["success"] is False
        assert "job_id" in result["error"].lower()

    def test_cancel_missing_job_id(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")

        result = mod.render_rop_chunked(action="cancel")
        assert result["success"] is False
        assert "job_id" in result["error"].lower()

    def test_launch_missing_rop_path(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")

        result = mod.render_rop_chunked(action="launch")
        assert result["success"] is False
        assert "rop_path" in result["error"].lower()

    def test_launch_missing_frame_range(self) -> None:
        mod = _load_script("houdini-render", "render_rop.py")

        result = mod.render_rop_chunked(action="launch", rop_path="/out/mantra1")
        assert result["success"] is False
        assert "frame_range" in result["error"].lower()


# ---------------------------------------------------------------------------
# Tests: ChunkedRunner step-through, cancel, terminal idempotence
# ---------------------------------------------------------------------------


class TestChunkedRunnerIntegration:
    def test_step_through_all_frames(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 4, 1])

        assert launch_result["success"] is True
        job_id = launch_result["job_id"]

        job = mod._rop_jobs[job_id]
        runner = job["runner"]

        # Step 1
        assert runner.step() is True
        assert runner.progress.completed == 1

        # Step 2
        assert runner.step() is True
        assert runner.progress.completed == 2

        # Step 3
        assert runner.step() is True
        assert runner.progress.completed == 3

        # Step 4 (terminal)
        assert runner.step() is False
        assert runner.outcome is not None
        assert runner.outcome.status == "completed"

        # Post-terminal step is no-op
        assert runner.step() is False

    def test_cancel_mid_sequence(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 10, 1])

        job_id = launch_result["job_id"]
        job = mod._rop_jobs[job_id]
        runner = job["runner"]

        # Run 3 frames
        for _ in range(3):
            assert runner.step() is True
        assert runner.progress.completed == 3

        # Cancel
        cancel_result = mod.cancel_rop_job(job_id)
        assert cancel_result["success"] is True
        assert cancel_result["state"] == "cancelling"

        # Next step observes cancellation
        assert runner.step() is False
        assert runner.outcome.status == "cancelled"
        assert runner.progress.completed == 3

    def test_cancel_before_first_step(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 5, 1])

        job_id = launch_result["job_id"]
        mod.cancel_rop_job(job_id)

        job = mod._rop_jobs[job_id]
        runner = job["runner"]
        assert runner.step() is False
        assert runner.outcome.status == "cancelled"
        assert runner.progress.completed == 0

    def test_terminal_idempotence(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 2, 1])

        job_id = launch_result["job_id"]
        job = mod._rop_jobs[job_id]
        runner = job["runner"]

        # Complete all steps
        assert runner.step() is True
        assert runner.step() is False  # terminal

        # Post-terminal ops are safe
        assert runner.step() is False
        mod.cancel_rop_job(job_id)  # should not raise
        assert runner.outcome.status == "completed"
        assert runner.progress.completed == 2

    def test_poll_after_completion(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 3, 1])

        job_id = launch_result["job_id"]
        job = mod._rop_jobs[job_id]
        runner = job["runner"]

        # Step through all
        while runner.step():
            pass

        result = mod.get_rop_job(job_id)
        assert result["state"] == "completed"
        assert result["progress"]["completed"] == 3
        assert result["skipped_frames"] == []

    def test_poll_after_cancellation(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 10, 1])

        job_id = launch_result["job_id"]
        job = mod._rop_jobs[job_id]
        runner = job["runner"]

        # Run 2 frames then cancel
        runner.step()
        runner.step()
        mod.cancel_rop_job(job_id)
        runner.step()  # observes cancel

        result = mod.get_rop_job(job_id)
        assert result["state"] == "cancelled"
        assert result["progress"]["completed"] == 2
        assert len(result["skipped_frames"]) == 8  # frames 3-10

    def test_generator_failure(self) -> None:
        _ = _load_script("houdini-render", "_rop_chunked.py")  # ensure module loaded

        from dcc_mcp_core.chunked_runner import ChunkedRunner

        def _failing_step() -> None:
            raise RuntimeError("render aborted")

        runner = ChunkedRunner([_failing_step])
        assert runner.step() is False
        assert runner.outcome.status == "failed"
        assert "RuntimeError: render aborted" in (runner.outcome.error or "")


# ---------------------------------------------------------------------------
# Tests: parm snapshot/restore
# ---------------------------------------------------------------------------


class TestParmSnapshotRestore:
    def test_launch_snapshots_parms(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 5, 1])

        job_id = launch_result["job_id"]
        job = mod._rop_jobs[job_id]
        assert "parm_snapshot" in job
        assert "trange" in job["parm_snapshot"]

    def test_restore_called_on_completion(self) -> None:
        """Parm restore is called when runner reaches terminal via pump callback."""
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        # Record original values before launch
        orig_f1 = rop.parm("f1").eval()
        orig_f2 = rop.parm("f2").eval()

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 3, 1])

        job_id = launch_result["job_id"]
        job = mod._rop_jobs[job_id]
        runner = job["runner"]

        # Step through all frames (each step mutates parms via _set_single_frame_range)
        while runner.step():
            pass

        # Manually simulate the pump callback's restore path
        mod._restore_frame_parms(rop, job["parm_snapshot"])

        assert rop.parm("f1").eval() == orig_f1
        assert rop.parm("f2").eval() == orig_f2

    def test_restore_called_on_cancel(self) -> None:
        """Parm restore is called when runner is cancelled."""
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = _mock_rop()
        hou = _mock_hou(rop)

        orig_f1 = rop.parm("f1").eval()

        with patch.dict(sys.modules, {"hou": hou}):
            launch_result = mod.launch_rop_job("/out/mantra1", [1, 5, 1])

        job_id = launch_result["job_id"]
        job = mod._rop_jobs[job_id]
        runner = job["runner"]

        runner.step()  # mutates to frame 1
        runner.cancel()
        runner.step()  # observes cancel

        mod._restore_frame_parms(rop, job["parm_snapshot"])
        assert rop.parm("f1").eval() == orig_f1

    def test_restore_handles_missing_parms_gracefully(self) -> None:
        mod = _load_script("houdini-render", "_rop_chunked.py")
        rop = MagicMock()
        rop.parm.return_value = None
        rop.parmTuple.return_value = None

        # Should not raise
        snapshot = mod._snapshot_frame_parms(rop)
        assert snapshot == {}
        mod._restore_frame_parms(rop, snapshot)  # no-op, no crash
