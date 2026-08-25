"""Regression tests for the Install SOP lifecycle security boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from dcc_mcp_houdini import _installer
from dcc_mcp_houdini.cli import main


def _legacy_synthetic_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "Side Effects Software" / "Houdini 20.5.487"
    executable = root / "bin" / ("houdini.exe" if sys.platform == "win32" else "houdini")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    modules = tmp_path / "shadow-modules"
    modules.mkdir()
    (modules / "hou.py").write_text(
        'def applicationVersionString():\n    return "20.5.487"\n',
        encoding="utf-8",
    )
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(modules) + (os.pathsep + existing if existing else ""))
    monkeypatch.setenv("DCC_MCP_HOUDINI_PACKAGES_DIR", str(tmp_path / "profile" / "packages"))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    return executable


def _install_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[Path, list[str], dict]:
    host = _legacy_synthetic_host(tmp_path, monkeypatch)
    host.write_bytes(b"houdini")
    hython = host.with_name("hython.exe" if sys.platform == "win32" else "hython")
    hython.write_bytes(b"hython")
    module_root = host.parents[1]
    hou_file = module_root / "houdini" / "python3.12libs" / "hou.py"
    adapter_file = tmp_path / "site-packages" / "dcc_mcp_houdini" / "__init__.py"
    core_file = tmp_path / "site-packages" / "dcc_mcp_core" / "__init__.py"
    for path in (hou_file, adapter_file, core_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic module\n", encoding="utf-8")
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
    common = ["--json", "--dcc-path", str(host), "--python", str(hython)]
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
        "host_executable": str(host.resolve()),
        "houdini_root": str(host.parents[1].resolve()),
        "hou_module_path": str(hou_file.resolve()),
        "adapter_module_path": str(adapter_file.resolve()),
        "core_module_path": str(core_file.resolve()),
    }
    monkeypatch.setattr(
        _installer,
        "query_runtime_state",
        lambda *_args, **_kwargs: {"entries": [entry]},
    )
    monkeypatch.setattr(
        _installer,
        "wait_for_sidecar_ready",
        lambda *_args, **_kwargs: {
            "success": True,
            "entry": entry,
            "probe": {"result": {"structuredContent": {"success": True, "context": context}}},
        },
    )
    monkeypatch.setattr(_installer, "_process_executable_path", lambda _pid: host.resolve())
    monkeypatch.setattr(_installer, "_process_start_identity", lambda _pid: "test-start-4242")
    assert main(["install", *common, "--yes"]) == 0
    report = json.loads(capsys.readouterr().out)
    return host, common, report


def test_preflight_rejects_empty_host_and_unrelated_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    host = _legacy_synthetic_host(tmp_path, monkeypatch)

    code = main(["install", "--json", "--dry-run", "--dcc-path", str(host), "--python", sys.executable])
    report = json.loads(capsys.readouterr().out)

    assert code == 10
    assert report["verify"]["failure_stage"] in {"host", "python"}


@pytest.mark.parametrize(
    "value",
    [
        "v0.20.14rc1",
        "garbage0.20.14suffix",
        " 0.20.14 ",
        "0.19",
        "0.20.14.1",
        "0.019.91",
        "9" * 5000 + ".19.91",
    ],
)
def test_versions_reject_noncanonical_or_unbounded_values(value: str) -> None:
    assert _installer._version_tuple(value, components=3) is None


def _real_probe_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path / "Houdini 20.5.487"
    host = root / "bin" / ("houdini.exe" if sys.platform == "win32" else "houdini")
    hython = root / "bin" / ("hython.exe" if sys.platform == "win32" else "hython")
    hou_file = root / "houdini" / "python3.12libs" / "hou.py"
    adapter_root = tmp_path / "site-packages"
    adapter_file = adapter_root / "dcc_mcp_houdini" / "__init__.py"
    core_file = adapter_root / "dcc_mcp_core" / "__init__.py"
    for path in (host, hython, hou_file, adapter_file, core_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# probe fixture\n", encoding="utf-8")
    payload = {
        "python_version": "3.12.10",
        "core_version": _installer.MIN_CORE_VERSION,
        "core_dist_version": _installer.MIN_CORE_VERSION,
        "adapter_version": _installer.__version__,
        "adapter_dist_version": _installer.__version__,
        "host_version": "20.5.487",
        "executable": str(hython.resolve()),
        "hou_file": str(hou_file.resolve()),
        "adapter_file": str(adapter_file.resolve()),
        "core_file": str(core_file.resolve()),
        "adapter_dist_root": str(adapter_root.resolve()),
        "core_dist_root": str(adapter_root.resolve()),
        "adapter_record": "dcc_mcp_houdini/__init__.py",
        "core_record": "dcc_mcp_core/__init__.py",
        "adapter_direct_url": None,
        "core_direct_url": None,
    }
    return host, hython, payload


def test_hython_probe_binds_executable_hom_and_distribution_origins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host, hython, payload = _real_probe_fixture(tmp_path)
    monkeypatch.setattr(
        _installer,
        "_run_bounded_command",
        lambda *_args, **_kwargs: {"success": True, "stdout": json.dumps(payload), "stderr": ""},
    )
    assert _installer._query_python(hython, host)["host_version"] == "20.5.487"

    payload["adapter_file"] = str((tmp_path / "shadow" / "dcc_mcp_houdini.py").resolve())
    Path(payload["adapter_file"]).parent.mkdir()
    Path(payload["adapter_file"]).write_text("# shadow\n", encoding="utf-8")
    with pytest.raises(_installer.LifecycleFailure, match="shadowed"):
        _installer._query_python(hython, host)


def test_hython_probe_rejects_same_site_root_modules_not_owned_by_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host, hython, payload = _real_probe_fixture(tmp_path)
    monkeypatch.setattr(
        _installer,
        "_run_bounded_command",
        lambda *_args, **_kwargs: {"success": True, "stdout": json.dumps(payload), "stderr": ""},
    )

    payload["adapter_record"] = None
    with pytest.raises(_installer.LifecycleFailure, match="RECORD|ownership"):
        _installer._query_python(hython, host)

    payload["adapter_record"] = "dcc_mcp_houdini/__init__.py"
    payload["core_record"] = "unrelated/core.py"
    with pytest.raises(_installer.LifecycleFailure, match="RECORD|ownership"):
        _installer._query_python(hython, host)


def test_hython_probe_accepts_only_exact_editable_direct_url_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host, hython, payload = _real_probe_fixture(tmp_path)
    editable = tmp_path / "adapter-checkout"
    adapter_file = editable / "src" / "dcc_mcp_houdini" / "__init__.py"
    adapter_file.parent.mkdir(parents=True)
    adapter_file.write_text("# editable adapter\n", encoding="utf-8")
    payload.update(
        {
            "adapter_file": str(adapter_file.resolve()),
            "adapter_record": None,
            "adapter_direct_url": {"url": editable.resolve().as_uri(), "dir_info": {"editable": True}},
        }
    )
    monkeypatch.setattr(
        _installer,
        "_run_bounded_command",
        lambda *_args, **_kwargs: {"success": True, "stdout": json.dumps(payload), "stderr": ""},
    )

    assert _installer._query_python(hython, host)["adapter_file"] == str(adapter_file.resolve())
    payload["adapter_direct_url"] = {
        "url": (tmp_path / "different-checkout").resolve().as_uri(),
        "dir_info": {"editable": True},
    }
    with pytest.raises(_installer.LifecycleFailure, match="editable ownership"):
        _installer._query_python(hython, host)


def test_hython_probe_rejects_hom_outside_selected_hython_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host, hython, payload = _real_probe_fixture(tmp_path)
    fake_hom = host.parents[1] / "operator" / "hou.py"
    fake_hom.parent.mkdir()
    fake_hom.write_text("# unrelated hom\n", encoding="utf-8")
    payload["hou_file"] = str(fake_hom.resolve())
    monkeypatch.setattr(
        _installer,
        "_run_bounded_command",
        lambda *_args, **_kwargs: {"success": True, "stdout": json.dumps(payload), "stderr": ""},
    )

    with pytest.raises(_installer.LifecycleFailure, match="HOM|Hython"):
        _installer._query_python(hython, host)


def test_dcc_path_rejects_hython_but_python_flag_accepts_it(tmp_path: Path) -> None:
    root = tmp_path / "Houdini 20.5.487"
    host = root / "bin" / ("houdini.exe" if sys.platform == "win32" else "houdini")
    hython = root / "bin" / ("hython.exe" if sys.platform == "win32" else "hython")
    host.parent.mkdir(parents=True)
    host.write_bytes(b"houdini")
    hython.write_bytes(b"hython")

    with pytest.raises(_installer.LifecycleFailure, match="interactive Houdini"):
        _installer._resolve_host(str(hython), {})
    assert _installer._resolve_host(str(root), {}) == host.resolve()
    assert _installer._resolve_python(str(hython), host, {}) == (hython.resolve(), "--python")


def test_hython_probe_timeout_is_a_stable_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host, hython, _payload = _real_probe_fixture(tmp_path)
    monkeypatch.setattr(
        _installer,
        "_run_bounded_command",
        lambda *_args, **_kwargs: {"success": False, "reason": "probe timed out"},
    )
    with pytest.raises(_installer.LifecycleFailure, match="timed out") as raised:
        _installer._query_python(hython, host)
    assert raised.value.exit_code == 10


def test_uninstall_refuses_unowned_empty_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    root = Path(report["plan"]["install_root"])
    victim = root / "operator-owned-empty"
    victim.mkdir()

    assert main(["uninstall", *common, "--yes"]) == 30
    failure = json.loads(capsys.readouterr().out)
    assert failure["verify"]["failure_stage"] == "receipt"
    assert victim.is_dir()
    assert root.is_dir()


def test_uninstall_rejects_forged_path_escape_and_preserves_victim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    receipt_path = Path(report["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    victim = receipt_path.parent / "operator-owned.txt"
    victim.write_text("keep\n", encoding="utf-8")
    receipt["ownership"]["files"][0]["path"] = "../operator-owned.txt"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert main(["uninstall", *common, "--yes"]) == 30
    failure = json.loads(capsys.readouterr().out)
    assert failure["verify"]["failure_stage"] == "receipt"
    assert victim.read_text(encoding="utf-8") == "keep\n"


def test_uninstall_rejects_managed_tree_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    root = Path(report["plan"]["install_root"])
    link = root / "operator-link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError as exc:
        pytest.skip("symlink creation is unavailable: {}".format(exc))

    assert main(["uninstall", *common, "--yes"]) == 30
    failure = json.loads(capsys.readouterr().out)
    assert failure["verify"]["failure_stage"] == "receipt"
    assert link.is_symlink()


def test_upgrade_readiness_is_deferred_without_rolling_back_static_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    receipt_path = Path(report["receipt_path"])
    previous = receipt_path.read_bytes()
    monkeypatch.setattr(_installer, "wait_for_sidecar_ready", lambda *_args, **_kwargs: {"success": False})

    assert main(["upgrade", *common, "--yes"]) == 0
    upgraded = json.loads(capsys.readouterr().out)
    assert upgraded["status"] == "ok"
    assert upgraded["steps"][-1] == {"id": "verify", "status": "pending"}
    assert upgraded["verify"]["failure_stage"] == "readiness"
    assert "previous_restored" not in upgraded
    assert receipt_path.is_file()
    assert receipt_path.read_bytes() != previous


def test_macos_profile_app_bundle_and_hython_discovery_are_consistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    applications = tmp_path / "Applications" / "Houdini"
    app = applications / "Houdini20.5.487.app"
    host = app / "Contents" / "MacOS" / "houdini"
    hython = app / "Contents" / "Resources" / "bin" / "hython"
    hou_file = app / "Contents" / "Resources" / "houdini" / "python3.11libs" / "hou.py"
    for path in (host, hython, hou_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"official-sidefx-file")
    monkeypatch.setattr(_installer.sys, "platform", "darwin")
    monkeypatch.setattr(_installer.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(_installer, "_MACOS_APPLICATIONS_ROOT", applications, raising=False)

    profile, packages = _installer._profile_paths("20.5.487", {})
    assert profile == (home / "Library" / "Preferences" / "houdini" / "20.5").resolve()
    assert packages == (profile / "packages").resolve()
    assert _installer._host_candidates({}) == (host.resolve(),)
    assert _installer._resolve_host(str(app), {}) == host.resolve()
    assert _installer._host_version(host.resolve()) == ("20.5.487", "path")
    assert _installer._resolve_python(None, host.resolve(), {}) == (hython.resolve(), "host_install")
    assert _installer._resolve_python(str(hython), host.resolve(), {}) == (hython.resolve(), "--python")
    _installer._require_genuine_hom_origin(hou_file.resolve(), host.resolve(), (3, 11, 9))


def test_upgrade_staging_failure_never_moves_prior_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    root = Path(report["plan"]["install_root"])
    package_file = Path(report["plan"]["packages_dir"]) / "dcc_mcp_houdini.json"
    receipt_path = Path(report["receipt_path"])
    root_before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    package_before = package_file.read_bytes()
    receipt_before = receipt_path.read_bytes()
    monkeypatch.setattr(
        _installer,
        "_expected_sources",
        lambda _ctx: (_ for _ in ()).throw(OSError("injected staging failure")),
    )

    assert main(["upgrade", *common, "--yes"]) == 30
    capsys.readouterr()
    assert {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()} == root_before
    assert package_file.read_bytes() == package_before
    assert receipt_path.read_bytes() == receipt_before


def test_partial_uninstall_failure_restores_all_owned_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    root = Path(report["plan"]["install_root"])
    receipt_path = Path(report["receipt_path"])
    package_file = Path(report["plan"]["packages_dir"]) / "dcc_mcp_houdini.json"
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    original = _installer.safe_remove_tree

    def partial_remove(path):
        candidate = Path(path)
        if candidate.name == "quarantine":
            next(iter(sorted(candidate.rglob("*.py")))).unlink()
            return {"success": False, "requires_restart": False, "message": "injected partial removal"}
        return original(path)

    monkeypatch.setattr(_installer, "safe_remove_tree", partial_remove)
    assert main(["uninstall", *common, "--yes"]) == 30
    capsys.readouterr()
    assert {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
    assert package_file.is_file()
    assert receipt_path.is_file()


def test_uninstall_permission_error_restores_after_partial_atomic_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    root = Path(report["plan"]["install_root"])
    package_file = Path(report["plan"]["packages_dir"]) / "dcc_mcp_houdini.json"
    receipt_path = Path(report["receipt_path"])
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    package_before = package_file.read_bytes()
    receipt_before = receipt_path.read_bytes()
    original_replace = _installer.os.replace
    injected = False

    def deny_registration(source, destination):
        nonlocal injected
        if not injected and Path(source).resolve() == package_file.resolve() and "quarantine" in str(destination):
            injected = True
            raise PermissionError("injected registration lock")
        return original_replace(source, destination)

    monkeypatch.setattr(_installer.os, "replace", deny_registration)
    assert main(["uninstall", *common, "--yes"]) == 30
    failure = json.loads(capsys.readouterr().out)
    assert failure["verify"]["failure_stage"] == "uninstall"
    assert {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
    assert package_file.read_bytes() == package_before
    assert receipt_path.read_bytes() == receipt_before


def test_verify_rejects_foreign_runtime_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _host, common, _report = _install_current(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(
        _installer,
        "query_runtime_state",
        lambda *_args, **_kwargs: {
            "entries": [
                {
                    "mcp_url": "http://127.0.0.1:18812/mcp",
                    "instance_id": "foreign",
                    "metadata": {"dcc_pid": 999999, "dcc_version": "19.5.1"},
                }
            ]
        },
    )
    monkeypatch.setattr(_installer, "wait_for_sidecar_ready", lambda *_args, **_kwargs: {"success": True})

    assert main(["verify", *common]) == 40
    failure = json.loads(capsys.readouterr().out)
    assert failure["verify"]["failure_stage"] == "readiness_identity"


def test_verify_rejects_pid_reuse_start_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    host, common, report = _install_current(tmp_path, monkeypatch, capsys)
    receipt = json.loads(Path(report["receipt_path"]).read_text(encoding="utf-8"))
    entry = {
        "mcp_url": "http://127.0.0.1:18812/mcp",
        "instance_id": "houdini-test-4242",
        "adapter_version": _installer.__version__,
        "metadata": {"dcc_pid": 4242, "dcc_version": "20.5.487"},
    }
    context = {
        "host_pid": 4242,
        "process_start_identity": "stale-process-start",
        "houdini_version_string": "20.5.487",
        "adapter_version": _installer.__version__,
        "ui_available": True,
        "host_executable": str(host.resolve()),
        "houdini_root": str(host.parents[1].resolve()),
        "hou_module_path": receipt["python"]["hou_module_path"],
        "adapter_module_path": receipt["python"]["adapter_module_path"],
        "core_module_path": receipt["python"]["core_module_path"],
    }
    monkeypatch.setattr(_installer, "query_runtime_state", lambda *_args, **_kwargs: {"entries": [entry]})
    monkeypatch.setattr(
        _installer,
        "wait_for_sidecar_ready",
        lambda *_args, **_kwargs: {
            "success": True,
            "entry": entry,
            "probe": {"result": {"structuredContent": {"success": True, "context": context}}},
        },
    )

    assert main(["verify", *common, "--instance-id", "houdini-test-4242", "--host-pid", "4242"]) == 40
    failure = json.loads(capsys.readouterr().out)
    assert failure["verify"]["failure_stage"] == "readiness_identity"
    assert "start identity" in failure["verify"]["failure_reason"]


def test_readiness_remediation_launches_exact_selected_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    host, common, _report = _install_current(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(_installer, "query_runtime_state", lambda *_args, **_kwargs: {"entries": []})
    assert main(["verify", *common]) == 40
    report = json.loads(capsys.readouterr().out)

    assert report["next_steps"][0]["command"] == [str(host.resolve())]
    assert report["next_steps"][1]["command"][1] == "verify"


def test_public_core_floor_is_a_real_released_version() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    runbook = (root / "install.md").read_text(encoding="utf-8")

    assert _installer.MIN_CORE_VERSION == "0.20.14"
    assert "dcc-mcp-core>=0.20.14,<1.0.0" in pyproject.replace(" ", "")
    assert "dcc-mcp-core >= 0.20.14,<1.0.0" in runbook


def test_all_public_lifecycle_results_validate_published_core_draft_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dcc_mcp_core.deployment import install_sop as core_install_sop
    from dcc_mcp_core.deployment import load_install_sop_schema

    root = Path(__file__).resolve().parents[1]
    schema_path = (
        Path(core_install_sop.__file__).resolve().parent.parent / "schemas" / "adapter-install-sop-v1.schema.json"
    )
    schema_bytes = schema_path.read_bytes()
    assert len(schema_bytes) == 4261
    assert hashlib.sha256(schema_bytes).hexdigest() == (
        "3ca25788439917b4d4c0617230a762f9797756b5b54f45c8c4149f975b90f904"
    )
    schema = load_install_sop_schema()
    assert schema == json.loads(schema_bytes)
    assert not (root / "src" / "dcc_mcp_houdini" / "_install_contract.py").exists()
    assert not (root / "tests" / "fixtures" / "adapter-install-sop-v1.schema.json").exists()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    _host, common, install_result = _install_current(tmp_path, monkeypatch, capsys)
    results = [install_result]
    for argv in (
        ["status", *common],
        ["verify", *common],
        ["upgrade", *common, "--dry-run"],
        ["uninstall", *common, "--dry-run"],
    ):
        main(argv)
        results.append(json.loads(capsys.readouterr().out))
    for result in results:
        validator.validate(result)

    missing = tmp_path / "missing" / "houdini.exe"
    assert main(["install", "--json", "--dry-run", "--dcc-path", str(missing)]) == 10
    validator.validate(json.loads(capsys.readouterr().out))
