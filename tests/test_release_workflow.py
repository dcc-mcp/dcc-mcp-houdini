"""Release workflow contract tests."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _release_workflow() -> dict:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
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
