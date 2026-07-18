"""Unit tests for the bundled-skill linter wrapper (``tools/lint_skills.py``).

These focus on the dcc-mcp-cli integration the runtime loader relies on:
parsing the CLI's structured JSON report and the ``--require-cli`` guard that
keeps CI from silently dropping to a weaker validator.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("lint_skills_under_test", ROOT / "tools" / "lint_skills.py")
lint_skills = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lint_skills)  # type: ignore[union-attr]


def _fake_completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["dcc-mcp-cli"], returncode=returncode, stdout=stdout, stderr="")


def test_require_cli_fails_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lint_skills, "_find_dcc_mcp_cli", lambda: None)

    errors = lint_skills.lint_skills(require_cli=True)

    assert len(errors) == 1
    assert "dcc-mcp-cli is required" in errors[0]


def test_cli_result_parses_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        '{"checked": 3, "errors": 0, "warnings": 0, "failed": false, '
        '"reports": [{"skill_dir": "houdini-scene", "issues": [], "errors": 0, "warnings": 0}]}'
    )
    monkeypatch.setattr(lint_skills, "_find_dcc_mcp_cli", lambda: "dcc-mcp-cli")
    monkeypatch.setattr(lint_skills, "_dcc_mcp_cli_version", lambda _cli: "dcc-mcp-cli 9.9.9")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(payload))

    result = lint_skills.lint_skills_with_cli(pathlib.Path("skills"))

    assert result is not None
    assert result.errors == []
    assert result.checked == 3
    assert result.failed is False
    assert result.version == "dcc-mcp-cli 9.9.9"


def test_cli_result_surfaces_errors_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        '{"checked": 1, "errors": 1, "warnings": 0, "failed": true, '
        '"reports": [{"skill_dir": "houdini-broken", "errors": 1, "warnings": 0, '
        '"issues": [{"severity": "error", "category": "schema", "message": "missing tools"}]}]}'
    )
    monkeypatch.setattr(lint_skills, "_find_dcc_mcp_cli", lambda: "dcc-mcp-cli")
    monkeypatch.setattr(lint_skills, "_dcc_mcp_cli_version", lambda _cli: "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(payload, returncode=1))

    result = lint_skills.lint_skills_with_cli(pathlib.Path("skills"))

    assert result is not None
    assert result.failed is True
    assert result.error_count == 1
    assert any("missing tools" in e for e in result.errors)


def test_cli_warnings_promoted_when_warnings_as_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        '{"checked": 1, "errors": 0, "warnings": 1, "failed": true, '
        '"reports": [{"skill_dir": "houdini-warn", "errors": 0, "warnings": 1, '
        '"issues": [{"severity": "warning", "category": "style", "message": "prefer lazy import"}]}]}'
    )
    monkeypatch.setattr(lint_skills, "_find_dcc_mcp_cli", lambda: "dcc-mcp-cli")
    monkeypatch.setattr(lint_skills, "_dcc_mcp_cli_version", lambda _cli: "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(payload, returncode=1))

    result = lint_skills.lint_skills_with_cli(pathlib.Path("skills"), warnings_as_errors=True)

    assert result is not None
    assert result.warning_count == 1
    assert any("prefer lazy import" in e for e in result.errors)


def test_non_json_cli_output_is_treated_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lint_skills, "_find_dcc_mcp_cli", lambda: "dcc-mcp-cli")
    monkeypatch.setattr(lint_skills, "_dcc_mcp_cli_version", lambda _cli: "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed("panic: boom", returncode=101))

    result = lint_skills.lint_skills_with_cli(pathlib.Path("skills"))

    assert result is not None
    assert result.failed is True
    assert result.errors == ["panic: boom"]


def test_module_exposes_expected_symbols() -> None:
    assert isinstance(lint_skills, types.ModuleType)
    assert hasattr(lint_skills, "CliLintResult")
    assert hasattr(lint_skills, "lint_skills_with_cli")


def test_houdini_conventions_reject_sibling_sys_path_mutation(
    tmp_path: pathlib.Path,
) -> None:
    skill_dir = tmp_path / "houdini-example"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (skill_dir / "tools.yaml").write_text(
        """tools:
- name: example
  source_file: scripts/example.py
""",
        encoding="utf-8",
    )
    (scripts_dir / "example.py").write_text(
        """from pathlib import Path
import sys

script_dir = str(Path(__file__).resolve().parent)
sys.path.insert(0, script_dir)
from _common import helper
""",
        encoding="utf-8",
    )
    front = {"metadata": {"dcc-mcp": {"tools": "tools.yaml"}}}
    errors = []

    lint_skills._lint_houdini_conventions(skill_dir, front, errors)

    assert errors == [
        "houdini-example/example: skill scripts must import sibling helpers "
        "directly; the shared runner owns script-directory import setup"
    ]
