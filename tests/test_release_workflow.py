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


def test_builds_verify_runtime_wheel_payload() -> None:
    required = (
        "dcc_mcp_houdini/_isolated_jobs.py",
        "dcc_mcp_houdini/_rop_jobs.py",
        "dcc_mcp_houdini/skills/houdini-render/scripts/_render_worker.py",
        "houdini-materials/SKILL.md",
    )
    for workflow in (_ci_workflow(), _release_workflow()):
        build_steps = workflow["jobs"]["build"]["steps"]
        verify_steps = [step for step in build_steps if step.get("name") == "Verify wheel contains bundled skills"]
        assert verify_steps, "build should verify wheel runtime payload"
        assert all(path in verify_steps[0]["run"] for path in required)


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


def test_release_quickinstall_can_pin_validated_core_version() -> None:
    workflow = _release_workflow()

    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["core_version"]["default"] == ""

    steps = workflow["jobs"]["quickinstall"]["steps"]
    assemble_steps = [step for step in steps if step.get("name") == "Assemble quickinstall ZIP"]
    verify_steps = [step for step in steps if step.get("name") == "Verify quickinstall version matrix"]
    assert assemble_steps, "quickinstall job should assemble release artifacts"
    assert verify_steps, "quickinstall job should verify release artifacts"
    assert "--core-version" in assemble_steps[0]["run"]
    assert "--expected-core-version" in verify_steps[0]["run"]


def _job_checkout(job: dict) -> dict:
    matches = [step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")]
    assert len(matches) == 1
    return matches[0]


def _immutable_target_step(job: dict) -> dict:
    matches = [step for step in job["steps"] if step.get("name") == "Verify immutable release target"]
    assert len(matches) == 1
    return matches[0]


def test_release_chain_cannot_be_cancelled_after_tag_creation() -> None:
    workflow = _release_workflow()

    assert workflow["concurrency"]["cancel-in-progress"] == "false"


def test_release_job_resolves_a_validated_tag_to_an_immutable_commit() -> None:
    workflow = _release_workflow()
    release = workflow["jobs"]["release-please"]

    assert release["outputs"]["tag_name"] == "${{ steps.target.outputs.tag_name }}"
    assert release["outputs"]["tag_sha"] == "${{ steps.target.outputs.tag_sha }}"
    assert release["outputs"]["version"] == "${{ steps.target.outputs.version }}"
    target_steps = [step for step in release["steps"] if step.get("id") == "target"]
    assert len(target_steps) == 1
    target = target_steps[0]
    script = target["run"]
    assert "steps.release.outputs.tag_name" in target["env"]["RELEASE_TAG"]
    assert "inputs.tag_name" in target["env"]["RELEASE_TAG"]
    assert "git/ref/tags/" in script
    assert "gh api" in script
    assert "tag_sha" in script
    assert "^v[0-9]+\\.[0-9]+\\.[0-9]+$" in script


def test_every_release_asset_job_binds_tag_sha_and_version_before_mutation() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]

    for name in ("build", "quickinstall", "publish", "attach-release-assets"):
        job = jobs[name]
        needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
        assert "release-please" in needs
        checkout = _job_checkout(job)
        assert checkout["with"]["ref"] == "${{ needs.release-please.outputs.tag_name }}"
        assert checkout["with"]["fetch-depth"] == "0"
        assert "github.ref" not in checkout["with"]["ref"]
        assert "inputs.tag_name" not in checkout["with"]["ref"]
        verify = _immutable_target_step(job)
        assert verify["env"] == {
            "EXPECTED_TAG": "${{ needs.release-please.outputs.tag_name }}",
            "EXPECTED_SHA": "${{ needs.release-please.outputs.tag_sha }}",
            "EXPECTED_VERSION": "${{ needs.release-please.outputs.version }}",
        }
        script = verify["run"]
        assert "git rev-parse HEAD" in script
        assert 'git rev-parse "${EXPECTED_TAG}^{commit}"' in script
        assert ".release-please-manifest.json" in script
        assert "src/dcc_mcp_houdini/__version__.py" in script


def test_publish_uses_oidc_only_and_jobs_keep_least_privilege() -> None:
    workflow = _release_workflow()
    release = workflow["jobs"]["release-please"]
    publish = workflow["jobs"]["publish"]
    attach = workflow["jobs"]["attach-release-assets"]
    workflow_text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert workflow["permissions"] == {"contents": "read"}
    assert release["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    assert attach["permissions"] == {"contents": "write"}
    assert "PYPI_API_TOKEN" not in workflow_text
    assert "secrets.PYPI_API_TOKEN" not in workflow_text
    publishers = [step for step in publish["steps"] if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")]
    assert len(publishers) == 1
    assert "password" not in publishers[0].get("with", {})
    attach_step = [step for step in attach["steps"] if step.get("uses", "").startswith("softprops/action-gh-release@")]
    assert attach_step[0]["with"]["tag_name"] == "${{ needs.release-please.outputs.tag_name }}"


def test_release_assets_are_guarded_before_immutable_upload() -> None:
    workflow = _release_workflow()
    attach_job = workflow["jobs"]["attach-release-assets"]
    steps = attach_job["steps"]

    assert attach_job["concurrency"] == {
        "group": "release-assets-${{ github.repository }}-${{ needs.release-please.outputs.tag_name }}",
        "cancel-in-progress": "false",
    }

    stage = [step for step in steps if step.get("name") == "Stage release asset guard"]
    guard = [step for step in steps if step.get("name") == "Guard immutable release assets"]
    upload = [step for step in steps if step.get("uses", "").startswith("softprops/action-gh-release@")]
    assert len(stage) == len(guard) == len(upload) == 1
    assert steps.index(stage[0]) < steps.index(guard[0]) < steps.index(upload[0])

    assert 'git show "${GITHUB_SHA}:tools/check_release_assets.py"' in stage[0]["run"]
    assert "$RUNNER_TEMP/check_release_assets.py" in stage[0]["run"]
    assert guard[0]["env"] == {
        "GH_HOST": "github.com",
        "GH_TOKEN": "${{ github.token }}",
        "EXPECTED_TAG": "${{ needs.release-please.outputs.tag_name }}",
    }
    guard_run = guard[0]["run"]
    assert 'python "$RUNNER_TEMP/check_release_assets.py"' in guard_run
    assert '--repository "$GITHUB_REPOSITORY"' in guard_run
    assert '--tag "$EXPECTED_TAG"' in guard_run
    assert '--pattern "dist/*"' in guard_run
    assert '--pattern "dist_houdini/*.zip"' in guard_run
    assert upload[0]["with"]["overwrite_files"] == "false"
    assert upload[0]["with"]["fail_on_unmatched_files"] == "true"
