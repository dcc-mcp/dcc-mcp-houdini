"""Mock-hou unit tests for foreground chunked ROP render (PIP-2789).

These tests exercise the ChunkedRunner integration for foreground multi-frame
ROP renders without requiring a real Houdini session.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(skill_name: str, script_name: str) -> Any:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(
        f"{skill_name}_{path.stem}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _mock_rop(path: str, name: str, type_name: str = "ifd") -> MagicMock:
    """Create a mock ROP node with the standard HOM interface."""
    rop = MagicMock()
    rop.path.return_value = path
    rop.name.return_value = name
    rop.type.return_value.name.return_value = type_name
    return rop


# ---------------------------------------------------------------------------
# build_per_frame_steps tests
# ---------------------------------------------------------------------------


class TestBuildPerFrameSteps:
    def test_three_frames_positive_step(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        steps = mod.build_per_frame_steps(MagicMock(), [1, 3, 1])
        assert len(steps) == 3
        assert steps[0]._frame == 1.0  # type: ignore[attr-defined]
        assert steps[1]._frame == 2.0  # type: ignore[attr-defined]
        assert steps[2]._frame == 3.0  # type: ignore[attr-defined]

    def test_three_frames_implicit_step(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        steps = mod.build_per_frame_steps(MagicMock(), [10, 12])
        assert len(steps) == 3
        assert steps[0]._frame == 10.0  # type: ignore[attr-defined]
        assert steps[1]._frame == 11.0  # type: ignore[attr-defined]
        assert steps[2]._frame == 12.0  # type: ignore[attr-defined]

    def test_single_frame_range(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        steps = mod.build_per_frame_steps(MagicMock(), [5, 5, 1])
        assert len(steps) == 1
        assert steps[0]._frame == 5.0  # type: ignore[attr-defined]

    def test_rejects_invalid_range(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        with pytest.raises(ValueError, match="step must move"):
            mod.build_per_frame_steps(MagicMock(), [5, 1, 1])

    def test_rejects_zero_step(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        with pytest.raises(ValueError, match="step must move"):
            mod.build_per_frame_steps(MagicMock(), [1, 5, 0])

    def test_each_step_calls_render_with_single_frame(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        rop = _mock_rop("/out/mantra1", "mantra1")
        steps = mod.build_per_frame_steps(rop, [1, 3, 1])
        for i, step in enumerate(steps):
            step()
            rop.render.assert_called_with(
                verbose=False,
                frame_range=(float(i + 1), float(i + 1), 1.0),
            )


# ---------------------------------------------------------------------------
# ChunkedRunner integration tests
# ---------------------------------------------------------------------------


class TestChunkedRopRunner:
    """Tests that exercise the full ChunkedRunner pipeline for ROP renders."""

    def test_step_through_all_frames(self) -> None:
        """ChunkedRunner steps through 4 frames and reaches 'completed'."""
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        mod = _load_script("houdini-render", "_render_common.py")
        rop = _mock_rop("/out/mantra1", "mantra1")
        steps = mod.build_per_frame_steps(rop, [1, 4, 1])
        runner = ChunkedRunner(steps)

        # Step 1
        assert runner.step() is True
        assert runner.progress.completed == 1

        # Step 2
        assert runner.step() is True
        assert runner.progress.completed == 2

        # Step 3
        assert runner.step() is True
        assert runner.progress.completed == 3

        # Step 4 (last)
        assert runner.step() is False  # terminal
        assert runner.outcome is not None
        assert runner.outcome.status == "completed"
        assert runner.progress.completed == 4

        # Post-terminal step is a no-op
        assert runner.step() is False

    def test_cancellation_mid_sequence(self) -> None:
        """Cancel after 2 of 5 frames produces 'cancelled' with partial progress."""
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        mod = _load_script("houdini-render", "_render_common.py")
        rop = _mock_rop("/out/mantra1", "mantra1")
        steps = mod.build_per_frame_steps(rop, [1, 5, 1])
        runner = ChunkedRunner(steps)

        # Run 2 frames
        assert runner.step() is True
        assert runner.step() is True
        assert runner.progress.completed == 2

        # Cancel
        runner.cancel()

        # Next step observes cancellation
        assert runner.step() is False
        assert runner.outcome is not None
        assert runner.outcome.status == "cancelled"
        assert runner.progress.completed == 2

    def test_cancellation_before_first_step(self) -> None:
        """Cancel before any step runs."""
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        mod = _load_script("houdini-render", "_render_common.py")
        rop = _mock_rop("/out/mantra1", "mantra1")
        steps = mod.build_per_frame_steps(rop, [1, 3, 1])
        runner = ChunkedRunner(steps)

        runner.cancel()
        assert runner.step() is False
        assert runner.outcome.status == "cancelled"
        assert runner.progress.completed == 0

    def test_terminal_idempotence(self) -> None:
        """step() and cancel() are safe after terminal state."""
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        mod = _load_script("houdini-render", "_render_common.py")
        rop = _mock_rop("/out/mantra1", "mantra1")
        steps = mod.build_per_frame_steps(rop, [1, 2, 1])
        runner = ChunkedRunner(steps)

        # Complete all steps
        assert runner.step() is True
        assert runner.step() is False  # terminal

        # Post-terminal operations are idempotent
        assert runner.step() is False
        runner.cancel()  # should not raise
        assert runner.outcome.status == "completed"
        assert runner.progress.completed == 2

    def test_generator_failure(self) -> None:
        """A failing step produces 'failed' outcome."""
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        def _failing_step() -> None:
            raise RuntimeError("render aborted")

        steps = [_failing_step]
        runner = ChunkedRunner(steps)

        assert runner.step() is False
        assert runner.outcome is not None
        assert runner.outcome.status == "failed"
        assert "RuntimeError: render aborted" in (runner.outcome.error or "")

    def test_single_frame_not_chunked(self) -> None:
        """A single frame range without multi-frame gap stays single-call."""
        mod = _load_script("houdini-render", "render_rop.py")

        mock_hou = MagicMock()
        rop = _mock_rop("/out/mantra1", "mantra1")
        mock_hou.node.return_value = rop

        # Setup parm to return a real string (not MagicMock) so
        # eval_first_parm and expanded_outputs work correctly.
        picture_parm = MagicMock()
        picture_parm.unexpandedString.return_value = "/renders/test.$F4.exr"
        rop.parm.return_value = picture_parm
        rop.parmTuple.return_value = None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop(
                "/out/mantra1", frame_range=[1, 1, 1], background=False
            )

        assert result["success"] is True
        assert result["context"]["execution_mode"] == "render"

    def test_solaris_stays_single_call(self) -> None:
        """Solaris usdrender_rop with multi-frame still uses single execute."""
        mod = _load_script("houdini-render", "render_rop.py")

        mock_hou = MagicMock()
        rop = _mock_rop(
            "/stage/rendersettings1", "rendersettings1", "usdrender_rop"
        )
        mock_hou.node.return_value = rop

        picture_parm = MagicMock()
        picture_parm.unexpandedString.return_value = "/renders/test.$F4.exr"
        rop.parm.return_value = picture_parm
        rop.parmTuple.return_value = None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop(
                "/stage/rendersettings1", frame_range=[1, 10, 1], background=False
            )

        assert result["success"] is True
        assert result["context"]["execution_mode"] == "execute"

    @pytest.mark.skip(reason="background path unchanged; tested in existing suite")
    def test_background_path_unchanged(self) -> None:
        """Background rendering (default) still uses subprocess path.

        The background subprocess path is unchanged by this PR and is
        covered by existing tests in the test suite.
        """


# ---------------------------------------------------------------------------
# Foreground job registry tests
# ---------------------------------------------------------------------------


class TestForegroundJobRegistry:
    def test_register_and_get_job(self) -> None:
        mod = _load_script("houdini-render", "_chunked_utils.py")
        from dcc_mcp_core.cancellation import CancelToken
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        steps = [lambda: None] * 10
        runner = ChunkedRunner(steps)
        token = CancelToken()
        job_id = mod._register_foreground_job(
            runner, token, "/out/mantra1", [1, 10, 1], 10
        )
        assert job_id.startswith("rop-fg-")

        job = mod.get_foreground_job(job_id)
        assert job is not None
        assert job["state"] == "running"
        assert job["rop_path"] == "/out/mantra1"
        assert job["progress"]["total"] == 10

    def test_get_unknown_job(self) -> None:
        mod = _load_script("houdini-render", "_chunked_utils.py")
        assert mod.get_foreground_job("rop-fg-nonexistent") is None

    def test_cancel_foreground_job(self) -> None:
        mod = _load_script("houdini-render", "_chunked_utils.py")
        from dcc_mcp_core.cancellation import CancelToken
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        steps = [lambda: None] * 5
        runner = ChunkedRunner(steps)
        token = CancelToken()
        job_id = mod._register_foreground_job(
            runner, token, "/out/mantra1", [1, 5, 1], 5
        )

        # Run 2 steps to ensure runner is still active
        assert runner.step() is True
        assert runner.step() is True

        result = mod.cancel_foreground_job(job_id)
        assert result is not None
        # cancel() sets the token; the next step() would observe it,
        # but get_foreground_job returns current state which is still
        # "running" until the checkpoint runs
        assert result["progress"]["completed"] == 2

    def test_cancel_unknown_job(self) -> None:
        mod = _load_script("houdini-render", "_chunked_utils.py")
        assert mod.cancel_foreground_job("rop-fg-ghost") is None

    def test_unregister_removes_job(self) -> None:
        mod = _load_script("houdini-render", "_chunked_utils.py")
        from dcc_mcp_core.cancellation import CancelToken
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        runner = ChunkedRunner([])
        token = CancelToken()
        job_id = mod._register_foreground_job(
            runner, token, "/out/mantra1", [1, 3, 1], 3
        )

        removed = mod._unregister_foreground_job(job_id)
        assert removed is not None
        assert mod.get_foreground_job(job_id) is None

    def test_terminal_job_reports_completed_frames(self) -> None:
        mod = _load_script("houdini-render", "_chunked_utils.py")
        from dcc_mcp_core.cancellation import CancelToken
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        steps = [lambda: None, lambda: None, lambda: None]
        runner = ChunkedRunner(steps)
        token = CancelToken()
        job_id = mod._register_foreground_job(
            runner, token, "/out/mantra1", [1, 3, 1], 3
        )

        # Complete all steps
        for _ in range(3):
            runner.step()

        job = mod.get_foreground_job(job_id)
        assert job["state"] == "completed"
        assert job["completed_frames"] == 3


# ---------------------------------------------------------------------------
# Cancel render_job.py integration
# ---------------------------------------------------------------------------


class TestCancelRenderJob:
    def test_cancel_foreground_via_cancel_render_job(self) -> None:
        """cancel_render_job detects 'rop-fg-' prefix and routes to foreground."""
        # Import _chunked_utils as the module name that cancel_render_job.py
        # will resolve via sys.path: just "_chunked_utils"
        utils_mod = _load_script("houdini-render", "_chunked_utils.py")
        # Re-register under the name cancel_render_job.py will see
        sys.modules["_chunked_utils"] = utils_mod

        mod = _load_script("houdini-render", "cancel_render_job.py")

        from dcc_mcp_core.cancellation import CancelToken
        from dcc_mcp_core.chunked_runner import ChunkedRunner

        steps = [lambda: None] * 3
        runner = ChunkedRunner(steps)
        token = CancelToken()
        job_id = utils_mod._register_foreground_job(
            runner, token, "/out/mantra1", [1, 3, 1], 3
        )

        # Run 2 steps, then cancel via cancel_render_job
        assert runner.step() is True
        assert runner.step() is True

        result = mod.cancel_render_job(job_id)
        assert result["success"] is True
        # cancel() sets the token, but state becomes 'cancelled' only
        # after the next step() checkpoints it
        assert result["context"]["progress"]["completed"] == 2

    def test_cancel_unknown_foreground(self) -> None:
        """Cancelling a non-existent foreground job returns 'unknown'."""
        # Pre-register _chunked_utils under the name cancel_render_job.py sees
        utils_mod = _load_script("houdini-render", "_chunked_utils.py")
        sys.modules["_chunked_utils"] = utils_mod

        mod = _load_script("houdini-render", "cancel_render_job.py")
        result = mod.cancel_render_job("rop-fg-000000000000")
        assert result["success"] is True
        assert result["context"]["state"] == "unknown"
