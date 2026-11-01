"""Contract tests for ``run_python_file`` execution/result status semantics.

Regression for the long-script status/result slice of issue #364 (Finding 1):
a synchronous escape-hatch script can report its own failure through
``result = {"success": False, ...}``. The tool must distinguish "the host job
reached a terminal state" from "the script's nested result.success=false", and
tell consumers that a client-side timeout is NOT a cancellation, so an
unattended agent does not queue a second destructive run behind the first.

All tests are synthetic: ``hou`` is mocked and no live Houdini host is used.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SCRIPT_DIR = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills" / "houdini-automation" / "scripts"


def _load_run_python_file() -> ModuleType:
    path = _SCRIPT_DIR / "run_python_file.py"
    spec = importlib.util.spec_from_file_location("skill_run_python_file_status", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rpf() -> ModuleType:
    return _load_run_python_file()


def _run(rpf: ModuleType, tmp_path: Path, source: str, **kwargs):
    script = tmp_path / "long_script.py"
    script.write_text(source, encoding="utf-8")
    with patch.dict(sys.modules, {"hou": MagicMock()}):
        return rpf.run_python_file(str(script), **kwargs)


class TestRunPythonFileStatusSemantics:
    def test_completed_job_distinguished_from_nested_failure(self, rpf, tmp_path: Path) -> None:
        result = _run(
            rpf,
            tmp_path,
            "result = {'success': False, 'error': 'cook diverged at frame 48'}\n",
        )
        # The host DID finish executing the file: transport success stays True.
        assert result["success"] is True
        assert result["context"]["execution_state"] == "completed"
        # ...but the script's own verdict is surfaced separately, so a consumer
        # reading only `success` no longer conflates the two.
        assert result["context"]["script_result_success"] is False

    def test_guidance_warns_timeout_is_not_cancellation(self, rpf, tmp_path: Path) -> None:
        result = _run(rpf, tmp_path, "result = {'success': True}\n")
        prompt = (result.get("prompt") or "").lower()
        assert "timeout" in prompt
        assert "cancel" in prompt
        assert "retry" in prompt

    def test_nested_success_surfaced(self, rpf, tmp_path: Path) -> None:
        result = _run(rpf, tmp_path, "result = {'success': True, 'frames': 48}\n")
        assert result["context"]["script_result_success"] is True

    @pytest.mark.parametrize("payload", ["result = 42", "result = 'ok'", "result = None"])
    def test_non_mapping_result_has_no_verdict(self, rpf, tmp_path: Path, payload: str) -> None:
        result = _run(rpf, tmp_path, payload + "\n")
        assert result["context"]["script_result_success"] is None

    def test_non_bool_success_key_is_not_a_verdict(self, rpf, tmp_path: Path) -> None:
        result = _run(rpf, tmp_path, "result = {'success': 1}\n")
        assert result["context"]["script_result_success"] is None

    @pytest.mark.parametrize("output_mode", ["full", "structured", "summary"])
    def test_status_present_in_all_output_modes(self, rpf, tmp_path: Path, output_mode: str) -> None:
        result = _run(rpf, tmp_path, "result = {'success': False}\n", output_mode=output_mode)
        assert result["context"]["execution_state"] == "completed"
        assert result["context"]["script_result_success"] is False

    def test_raising_script_marks_exception_state(self, rpf, tmp_path: Path) -> None:
        result = _run(rpf, tmp_path, "raise RuntimeError('boom')\n")
        assert result["success"] is False
        assert result["context"]["execution_state"] == "exception"

    def test_input_rejection_is_not_started(self, rpf, tmp_path: Path) -> None:
        result = _run(rpf, tmp_path, "result = None\n", output_mode="invalid-mode")
        assert result["success"] is False
        assert result["context"]["execution_state"] == "not_started"

    def test_hou_unavailable_is_not_started(self, rpf, tmp_path: Path) -> None:
        script = tmp_path / "long_script.py"
        script.write_text("result = {'success': True}\n", encoding="utf-8")
        with patch.dict(sys.modules, {"hou": None}):
            result = rpf.run_python_file(str(script))
        assert result["success"] is False
        assert result["context"]["execution_state"] == "not_started"

    def test_nested_failure_does_not_flip_transport_success(self, rpf, tmp_path: Path) -> None:
        # Backward compatibility: a completed run stays a transport success; the
        # verdict is a separate explicit field, not an overload of `success`.
        ok = _run(rpf, tmp_path, "result = {'success': True}\n")
        failed = _run(rpf, tmp_path, "result = {'success': False}\n")
        assert ok["success"] is True and failed["success"] is True
        assert ok["context"]["script_result_success"] is True
        assert failed["context"]["script_result_success"] is False
