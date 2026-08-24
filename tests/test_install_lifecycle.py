"""Agent-first install lifecycle contract tests."""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

from dcc_mcp_houdini.cli import main


def _synthetic_host(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "Side Effects Software" / "Houdini 20.5.487"
    executable = root / "bin" / ("houdini.exe" if sys.platform == "win32" else "houdini")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    python_modules = tmp_path / "hython-modules"
    python_modules.mkdir(exist_ok=True)
    (python_modules / "hou.py").write_text(
        'def applicationVersionString():\n    return "20.5.487"\n',
        encoding="utf-8",
    )
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(python_modules) + (os.pathsep + existing if existing else ""))
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
            sys.executable,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == 1
    assert payload["status"] == "planned"
    assert payload["dcc_type"] == "houdini"
    assert payload["plan"]["host_version"] == "20.5.487"
    assert Path(payload["plan"]["interpreter"]).resolve() == Path(sys.executable).resolve()
    assert [step["id"] for step in payload["steps"]] == ["preflight", "install", "verify"]
    assert payload["next_steps"][0]["command"][:3] == ["dcc-mcp-houdini", "install", "--json"]
    assert payload["verify"] == {
        "directly_usable": False,
        "failure_stage": None,
        "failure_reason": None,
    }
    assert not packages_dir.exists()
    assert not Path(payload["receipt_path"]).exists()


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
    common = ["--json", "--dcc-path", str(host), "--python", sys.executable]

    assert main(["install", *common, "--yes"]) == 40
    installed = json.loads(capsys.readouterr().out)
    assert installed["status"] == "partial"
    assert installed["verify"]["failure_stage"] == "readiness"
    receipt_path = Path(installed["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["host"]["version"] == "20.5.487"
    assert receipt["python"]["path"] == str(Path(sys.executable).resolve())
    assert all(len(item["sha256"]) == 64 for item in receipt["files"])
    install_root = Path(receipt["install_root"])
    package_file = Path(receipt["package_file"])
    assert package_file.is_file()
    assert (install_root / "scripts" / "123.py").is_file()
    bootstrap = (install_root / "scripts" / "dcc_mcp_houdini_bootstrap.py").read_text(encoding="utf-8")
    assert "capture_bootstrap_errors" in bootstrap
    before = {path: path.read_bytes() for path in install_root.rglob("*") if path.is_file()}

    assert main(["install", *common, "--yes"]) == 40
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

    exit_code = main(["install", "--json", "--yes", "--dcc-path", str(host), "--python", sys.executable])

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 10
    assert result["verify"]["failure_stage"] == "partial"
    assert (packages / "dcc_mcp_houdini.json").read_text(encoding="utf-8") == "{}\n"


def test_preflight_rejects_an_interpreter_without_houdini_hom(monkeypatch, tmp_path: Path, capsys) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))
    monkeypatch.delenv("PYTHONPATH")

    code = main(["install", "--json", "--dry-run", "--dcc-path", str(host), "--python", sys.executable])
    result = json.loads(capsys.readouterr().out)

    assert code == 10
    assert result["verify"]["failure_stage"] == "python"
    assert "import check failed" in result["verify"]["failure_reason"]
    assert not packages.exists()


def test_upgrade_requires_an_existing_receipt(monkeypatch, tmp_path: Path, capsys) -> None:
    host = _synthetic_host(tmp_path, monkeypatch)
    packages = tmp_path / "profile" / "packages"
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(packages))

    code = main(["upgrade", "--json", "--dry-run", "--dcc-path", str(host), "--python", sys.executable])
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
    common = ["--json", "--dcc-path", str(host), "--python", sys.executable]
    assert main(["install", *common, "--yes"]) == 40
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
    common = ["--json", "--dcc-path", str(host), "--python", sys.executable]
    assert main(["install", *common, "--yes"]) == 40
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

    code = main(["install", "--json", "--yes", "--dcc-path", str(host), "--python", sys.executable])
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
    assert "Install lifecycle smoke" in workflow
    assert "python -m pytest tests/test_install_lifecycle.py" in workflow
