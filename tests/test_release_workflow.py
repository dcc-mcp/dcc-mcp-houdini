"""Release workflow contract tests."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _release_workflow() -> dict:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    return yaml.load(text, Loader=yaml.BaseLoader)


def _ci_workflow() -> dict:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    return yaml.load(text, Loader=yaml.BaseLoader)


def test_release_workflow_can_backfill_pypi_for_existing_tag() -> None:
    workflow = _release_workflow()

    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["publish_to_pypi"]["type"] == "boolean"
    assert inputs["publish_to_pypi"]["default"] == "false"

    publish_job = workflow["jobs"]["publish"]
    assert "inputs.tag_name != ''" in publish_job["if"]
    assert "inputs.publish_to_pypi == true" in publish_job["if"]


def test_release_build_verifies_bundled_skills_before_publish() -> None:
    workflow = _release_workflow()
    build_steps = workflow["jobs"]["build"]["steps"]
    verify_steps = [step for step in build_steps if step.get("name") == "Verify wheel contains bundled skills"]
    assert verify_steps, "release build should verify wheel skill payload"
    assert "houdini-materials/SKILL.md" in verify_steps[0]["run"]


def test_release_please_updates_runtime_version_file() -> None:
    config = yaml.safe_load((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    extra_files = config["packages"]["."]["extra-files"]
    version_file = ROOT / "src" / "dcc_mcp_houdini" / "__version__.py"

    assert "src/dcc_mcp_houdini/__version__.py" in extra_files
    assert "x-release-please-version" in version_file.read_text(encoding="utf-8")


def test_quickinstall_jobs_verify_version_matrix() -> None:
    for workflow in (_ci_workflow(), _release_workflow()):
        steps = workflow["jobs"]["quickinstall"]["steps"]
        verify_steps = [step for step in steps if step.get("name") == "Verify quickinstall version matrix"]
        assert verify_steps, "quickinstall job should verify artifact version matrix"
        assert "--verify-zip" in verify_steps[0]["run"]
