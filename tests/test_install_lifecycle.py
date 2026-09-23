"""Agent-first install lifecycle contract tests."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from dcc_mcp_houdini import _installer
from dcc_mcp_houdini.cli import main


def _hython_for(host: Path) -> Path:
    return host.with_name("hython.exe" if sys.platform == "win32" else "hython")


def _synthetic_host(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "Side Effects Software" / "Houdini 20.5.487"
    executable = root / "bin" / ("houdini.exe" if sys.platform == "win32" else "houdini")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"houdini")
    hython = _hython_for(executable)
    hython.write_bytes(b"hython")
    modules = tmp_path / "hython-modules"
    modules.mkdir(exist_ok=True)
    hou_file = modules / "hou.py"
    adapter_file = modules / "dcc_mcp_houdini.py"
    core_file = modules / "dcc_mcp_core.py"
    for path in (hou_file, adapter_file, core_file):
        path.write_text("# synthetic module\n", encoding="utf-8")
    from dcc_mcp_houdini import _installer

    monkeypatch.setattr(
        _installer,
        "_query_python",
        lambda _path, _host: {
            "python_version": "3.12.10",
            "core_version": _installer.MIN_CORE_VERSION,
            "adapter_version": _installer.__version__,
            "host_version": "20.5.487",
            "executable": str(hython.resolve()),
            "hou_file": str(hou_file.resolve()),
            "adapter_file": str(adapter_file.resolve()),
            "core_file": str(core_file.resolve()),
        },
    )
    entry = {
        "mcp_url": "http://127.0.0.1:18812/mcp",
        "instance_id": "houdini-test-4242",
        "adapter_version": _installer.__version__,
        "metadata": {"dcc_pid": 4242, "dcc_version": "20.5.487"},
    }
    context = {
        "host_pid": 4242,
        "process_start_identity": "test-start-4242",
        "houdini_version_string": "20.5.487",
        "adapter_version": _installer.__version__,
        "ui_available": True,
        "host_executable": str(executable.resolve()),
        "houdini_root": str(executable.parents[1].resolve()),
        "hou_module_path": str(hou_file.resolve()),
        "adapter_module_path": str(adapter_file.resolve()),
        "core_module_path": str(core_file.resolve()),
    }
    readiness = {
        "success": True,
        "entry": entry,
        "probe": {"result": {"structuredContent": {"success": True, "context": context}}},
    }
    monkeypatch.setattr(_installer, "query_runtime_state", lambda *_args, **_kwargs: {"entries": [entry]})
    monkeypatch.setattr(_installer, "wait_for_sidecar_ready", lambda *_args, **_kwargs: readiness)
    monkeypatch.setattr(_installer, "_process_executable_path", lambda _pid: executable.resolve())
    monkeypatch.setattr(_installer, "_process_start_identity", lambda _pid: "test-start-4242")
    return executable


def test_install_dry_run_emits_contract_without_mutation(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    host_executable = _synthetic_host(tmp_path, monkeypatch)
    packages_dir = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages_dir))

    exit_code = main(
        [
            "install",
            "--json",
            "--dry-run",
            "--dcc-path",
            str(host_executable),
            "--python",
            str(_hython_for(host_executable)),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == _installer.report_schema_version()
    assert payload["status"] == "planned"
    assert payload["dcc_type"] == "houdini"
    assert payload["plan"]["host_version"] == "20.5.487"
    assert Path(payload["plan"]["interpreter"]).resolve() == _hython_for(host_executable).resolve()
    assert [step["id"] for step in payload["steps"]] == ["preflight", "install", "verify"]
    assert payload["next_steps"][0]["command"][:3] == ["dcc-mcp-houdini", "install", "--json"]
    assert payload["verify"] == {
        "directly_usable": False,
        "failure_stage": None,
        "failure_reason": None,
    }
    assert not packages_dir.exists()
    assert not Path(payload["receipt_path"]).exists()


def test_cold_install_without_live_registry_commits_and_returns_continuation(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "empty-registry"))
    monkeypatch.setattr(_installer, "query_runtime_state", lambda *_args, **_kwargs: {"entries": []})
    monkeypatch.setattr(
        _installer,
        "wait_for_sidecar_ready",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no live entry must not be probed")),
    )
    common = ["--json", "--dcc-path", str(host), "--python", str(_hython_for(host))]

    assert main(["install", *common, "--yes"]) == 0
    installed = json.loads(capsys.readouterr().out)

    assert installed["status"] == "ok"
    assert installed["verify"]["directly_usable"] is False
    assert installed["verify"]["failure_stage"] == "readiness"
    assert installed["steps"][-1] == {"id": "verify", "status": "pending"}
    assert [step["id"] for step in installed["next_steps"]] == [
        "start_selected_houdini",
        "verify_selected_houdini",
    ]
    assert Path(installed["receipt_path"]).is_file()
    assert Path(installed["plan"]["install_root"]).is_dir()
    assert (packages / "dcc_mcp_houdini.json").is_file()

    assert main(["verify", *common]) == 40
    verify = json.loads(capsys.readouterr().out)
    assert verify["status"] == "failed"
    assert verify["verify"]["failure_stage"] == "readiness"
    assert Path(installed["receipt_path"]).is_file()


def test_receipt_round_trip_is_idempotent_and_uninstall_is_receipt_driven(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("DCC_MCP_INSTALL_VERIFY_TIMEOUT", "0.01")
    common = ["--json", "--dcc-path", str(host), "--python", str(_hython_for(host))]

    assert main(["install", *common, "--yes"]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["status"] == "ok"
    assert installed["verify"]["directly_usable"] is True
    receipt_path = Path(installed["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["host"]["version"] == "20.5.487"
    assert receipt["python"]["path"] == str(_hython_for(host).resolve())
    assert all(len(item["sha256"]) == 64 for item in receipt["files"])
    install_root = Path(receipt["install_root"])
    package_file = Path(receipt["package_file"])
    assert package_file.is_file()
    assert (install_root / "scripts" / "123.py").is_file()
    bootstrap = (install_root / "scripts" / "dcc_mcp_houdini_bootstrap.py").read_text(encoding="utf-8")
    assert "capture_bootstrap_errors" in bootstrap
    before = {path: path.read_bytes() for path in install_root.rglob("*") if path.is_file()}

    assert main(["install", *common, "--yes"]) == 0
    capsys.readouterr()
    assert {path: path.read_bytes() for path in install_root.rglob("*") if path.is_file()} == before
    assert main(["status", *common]) == 0
    assert json.loads(capsys.readouterr().out)["install_state"] == "current"

    assert main(["uninstall", *common]) == 0
    capsys.readouterr()
    assert receipt_path.is_file()
    assert main(["uninstall", *common, "--yes"]) == 0
    removed = json.loads(capsys.readouterr().out)
    assert removed["status"] == "ok"
    assert not install_root.exists()
    assert not package_file.exists()
    assert not receipt_path.exists()
    assert main(["uninstall", *common, "--yes"]) == 0
    capsys.readouterr()


def test_partial_unreceipted_package_fails_closed(monkeypatch, tmp_path: Path, capsys) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    packages.mkdir(parents=True)
    (packages / "dcc_mcp_houdini.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))

    exit_code = main(["install", "--json", "--yes", "--dcc-path", str(host), "--python", str(_hython_for(host))])

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 10
    assert result["verify"]["failure_stage"] == "partial"
    assert (packages / "dcc_mcp_houdini.json").read_text(encoding="utf-8") == "{}\n"


def test_preflight_rejects_an_interpreter_without_houdini_hom(monkeypatch, tmp_path: Path, capsys) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))
    from dcc_mcp_houdini import _installer

    monkeypatch.setattr(
        _installer,
        "_query_python",
        lambda _path, _host: (_ for _ in ()).throw(
            _installer.LifecycleFailure("python", "Target interpreter import check failed: no HOM")
        ),
    )

    code = main(["install", "--json", "--dry-run", "--dcc-path", str(host), "--python", str(_hython_for(host))])
    result = json.loads(capsys.readouterr().out)

    assert code == 10
    assert result["verify"]["failure_stage"] == "python"
    assert "import check failed" in result["verify"]["failure_reason"]
    assert not packages.exists()


def test_upgrade_requires_an_existing_receipt(monkeypatch, tmp_path: Path, capsys) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))

    code = main(["upgrade", "--json", "--dry-run", "--dcc-path", str(host), "--python", str(_hython_for(host))])
    result = json.loads(capsys.readouterr().out)

    assert code == 10
    assert result["verify"]["failure_stage"] == "upgrade"
    assert "use install" in result["verify"]["failure_reason"]
    assert not packages.exists()


def test_modified_receipted_file_is_preserved_on_uninstall(monkeypatch, tmp_path: Path, capsys) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = ["--json", "--dcc-path", str(host), "--python", str(_hython_for(host))]
    assert main(["install", *common, "--yes"]) == 0
    installed = json.loads(capsys.readouterr().out)
    receipt_path = Path(installed["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    modified = Path(receipt["files"][0]["path"])
    modified.write_text("# operator change\n", encoding="utf-8")

    assert main(["uninstall", *common, "--yes"]) == 30
    failure = json.loads(capsys.readouterr().out)
    assert failure["verify"]["failure_stage"] == "receipt"
    assert modified.is_file()
    assert receipt_path.is_file()


def test_failed_upgrade_restores_previous_root_package_and_receipt(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = ["--json", "--dcc-path", str(host), "--python", str(_hython_for(host))]
    assert main(["install", *common, "--yes"]) == 0
    installed = json.loads(capsys.readouterr().out)
    receipt_path = Path(installed["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    install_root = Path(receipt["install_root"])
    package_file = Path(receipt["package_file"])
    old_root = {path.relative_to(install_root): path.read_bytes() for path in install_root.rglob("*") if path.is_file()}
    old_package = package_file.read_bytes()
    old_receipt = receipt_path.read_bytes()

    from dcc_mcp_houdini import _installer

    monkeypatch.setattr(
        _installer,
        "_write_json_atomic",
        lambda _path, _value: (_ for _ in ()).throw(OSError("injected receipt failure")),
    )
    assert main(["upgrade", *common, "--yes"]) == 30
    failed = json.loads(capsys.readouterr().out)

    assert failed["verify"]["failure_stage"] == "install"
    assert {
        path.relative_to(install_root): path.read_bytes() for path in install_root.rglob("*") if path.is_file()
    } == old_root
    assert package_file.read_bytes() == old_package
    assert receipt_path.read_bytes() == old_receipt


def test_restart_exit_requires_core_lock_evidence(monkeypatch, tmp_path: Path, capsys) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))
    from dcc_mcp_houdini import _installer

    monkeypatch.setattr(
        _installer,
        "inspect_install_root",
        lambda path: {
            "success": True,
            "status": "requires_restart",
            "requires_restart": True,
            "locked_path": str(Path(path) / "loaded.pyd"),
        },
    )

    code = main(["install", "--json", "--yes", "--dcc-path", str(host), "--python", str(_hython_for(host))])
    result = json.loads(capsys.readouterr().out)
    assert code == 50
    assert result["status"] == "requires_restart"
    assert result["lock"]["locked_path"].endswith("loaded.pyd")
    assert not packages.exists()


def test_generated_hooks_capture_bootstrap_errors_without_importing_hou_off_host() -> None:
    from dcc_mcp_houdini import _installer

    bootstrap = _installer._bootstrap_source(Path("logs"))
    hook = _installer._hook_source(Path("logs"))

    assert "capture_bootstrap_errors" in bootstrap
    assert 'phase="startup"' in bootstrap
    assert "import hou" in bootstrap
    assert "capture_bootstrap_errors" in hook
    assert 'phase="startup-hook"' in hook
    assert "bootstrap_and_start" in hook
    compile(bootstrap, "<houdini-bootstrap>", "exec")
    compile(hook, "<houdini-hook>", "exec")


def test_quickinstall_bootstrap_uses_staged_vendor_and_error_capture() -> None:
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging" / "assemble_houdini_package.py"))
    bootstrap = module["_bootstrap_py"]()
    startup = module["_startup_py"]()

    assert "safe_replace_tree" in bootstrap
    assert "shutil.rmtree(str(vendor_dir))" not in bootstrap
    assert "capture_bootstrap_errors" in bootstrap
    assert "capture_bootstrap_errors" in startup


def test_runbook_and_ci_cover_standard_lifecycle() -> None:
    root = Path(__file__).resolve().parents[1]
    runbook = (root / "install.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for heading in (
        "## Requirements",
        "## Supported versions",
        "## Agent quick path",
        "## Manual path",
        "## Verify",
        "## Upgrade",
        "## Uninstall",
        "## Troubleshooting",
    ):
        assert heading in runbook
    for platform_name in ("Windows", "macOS", "Linux"):
        assert platform_name in runbook
    for verb in ("install", "status", "verify", "upgrade", "uninstall"):
        assert "dcc-mcp-houdini {}".format(verb) in runbook
    assert "Python 3.7+ on Windows/Linux and Python" in runbook
    assert "3.8+ on macOS" in runbook
    assert "~/Library/Preferences/houdini/<version>/packages" in runbook
    assert "marks the verify step `pending`" in runbook
    assert "Install lifecycle smoke" in workflow
    assert "python -m pytest tests/test_install_lifecycle.py" in workflow


def test_report_schema_version_follows_cores_published_document(monkeypatch):
    """The report field is the ``const`` Core enforces, not a literal of ours."""
    monkeypatch.setattr(
        _installer,
        "load_install_sop_schema",
        lambda: {"properties": {"schema_version": {"const": 7}}},
    )

    assert _installer.report_schema_version() == 7


def test_report_schema_version_ignores_cores_artifact_revision():
    """Core's exported constant is the artifact revision, not the report field.

    Core 0.20.34 exports ``INSTALL_SOP_SCHEMA_VERSION = 2`` (the ``-v2`` artifact revision)
    while the report field must stay at the document's ``const`` of 1, because v2 only adds an
    optional ``catalog`` object. These are separate quantities that merely agreed while both
    were 1, so the constant must never reach the report.
    """
    assert _installer.report_schema_version() == 1


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Install SOP schema integrity error: schema_digest_mismatch"),
        OSError("schema file unreadable"),
        ValueError("schema document is not valid JSON"),
    ],
)
def test_report_schema_version_survives_schema_read_failure(monkeypatch, error):
    """An unhealthy Core must not stop the CLI from emitting a report.

    Core verifies its schema document with a SHA-256 digest and raises on a missing, tampered,
    or unparsable document. Broken installs are exactly the situation this CLI exists to
    report on, so the read failure has to degrade to the fallback instead of propagating.
    """
    monkeypatch.setattr(_installer, "load_install_sop_schema", _raise(error))

    assert _installer.report_schema_version() == _installer.FALLBACK_REPORT_SCHEMA_VERSION


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        '{"properties": {}}',
        {},
        {"properties": []},
        {"properties": {"schema_version": []}},
        {"properties": {"schema_version": {}}},
        {"properties": {"schema_version": {"const": "1"}}},
        {"properties": {"schema_version": {"const": True}}},
    ],
)
def test_report_schema_version_survives_malformed_document(monkeypatch, document):
    """A schema document of the wrong shape must degrade, not raise.

    Core 0.20.14 -- the floor of this adapter's pin -- loads the schema with a bare
    ``json.loads``: no type check, no digest check. So a document that is perfectly valid
    JSON can still be shaped unlike a schema, and walking it blindly raises AttributeError
    outside the read ``except`` above, which no caller catches.
    """
    monkeypatch.setattr(_installer, "load_install_sop_schema", lambda: document)

    assert _installer.report_schema_version() == _installer.FALLBACK_REPORT_SCHEMA_VERSION


def _raise(error: Exception):
    def _raiser():
        raise error

    return _raiser


def test_receipt_schema_version_is_a_separate_contract():
    """The receipt is its own document, not the Install SOP report.

    Both carry a ``schema_version`` that equals 1, which reads as a contradiction. They are
    unrelated documents: the Install SOP report follows the artifact Core publishes, while the
    receipt describes the installed package and owns its own revision.
    """
    assert _installer.RECEIPT_SCHEMA_VERSION == 1


def test_core_dependency_stays_pinned_below_the_next_minor():
    """``<1.0.0`` admits any future Core minor, which is how 0.20.34 shipped unannounced.

    Both bounds are derived from ``MIN_CORE_VERSION`` rather than spelled out, so a
    legitimate Core bump only moves that constant instead of turning this assertion red.
    """
    import re

    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    floor = _installer._version_tuple(_installer.MIN_CORE_VERSION)
    assert floor is not None
    core = re.search(r'"dcc-mcp-core>=(?P<lower>[0-9.]+),<(?P<upper>[0-9.]+)"', pyproject)

    assert core is not None
    assert core.group("lower") == _installer.MIN_CORE_VERSION
    assert core.group("upper") == "{}.{}.0".format(floor[0], floor[1] + 1)


def _ci_workflow():
    """Parsed ``.github/workflows/ci.yml`` for the repository under test."""
    import yaml

    root = Path(__file__).resolve().parents[1]
    return yaml.safe_load((root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def test_ci_core_latest_job_resolves_a_real_core_version():
    """The early-warning job must fail loudly rather than test an empty pin.

    The rest of this workflow pins Core to ``DCC_MCP_CORE_FLOOR``, which keeps it reproducible
    but also holds it at 0.20.14 -- the defect stayed invisible here purely because of that
    pin, so this job is the only thing that can see it.
    """
    job = _ci_workflow()["jobs"]["core-latest"]
    resolve = [step for step in job["steps"] if step.get("id") == "core"]
    assert resolve, "core-latest job has no version resolution step"

    script = resolve[0]["run"]
    assert "exit 1" in script, "empty version resolution must fail the job"
    assert "::error::" in script
