"""Official CLI contract and no-clobber publication tests, without a Houdini host."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_SKILL = Path(__file__).resolve().parents[1] / "src/dcc_mcp_houdini/skills/houdini-render"


def _header(width=64, height=32, version=2, payload=b"no real pixel codec in this fixture"):
    field = b"dataWindow\0box2i\0" + struct.pack("<I4i", 16, 0, 0, width - 1, height - 1)
    return b"\x76\x2f\x31\x01" + struct.pack("<I", version) + field + b"\0" + payload


@pytest.fixture
def operation(tmp_path, monkeypatch):
    script = _SKILL / "scripts/denoise_image.py"
    spec = importlib.util.spec_from_file_location("test_denoise_operation", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    root = tmp_path / "houdini"
    (root / "bin").mkdir(parents=True)
    utility = root / "bin" / ("idenoise.exe" if os.name == "nt" else "idenoise")
    utility.write_bytes(b"official utility path fixture, not executed")
    monkeypatch.setenv("HFS", str(root))
    source, target = tmp_path / "beauty.exr", tmp_path / "denoised.exr"
    source.write_bytes(_header())
    return module, source, target, utility


def _run_success(command, **kwargs):
    Path(command[2]).write_bytes(_header(payload=b"denoised fixture payload, not pixel decoded"))
    kwargs["stdout"].write(b"official denoiser completed\n")
    return SimpleNamespace(returncode=0)


def test_official_arguments_source_preservation_and_receipt(operation, monkeypatch):
    module, source, target, utility = operation
    original = source.read_bytes()
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return _run_success(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.denoise_image(
        str(source),
        str(target),
        albedo_plane="basecolor",
        normal_plane="hitN",
        aovs=["diffuse", "indirectDiffuse"],
        force_cpu=True,
    )
    assert result["success"], result
    context = result["context"]
    command, options = calls[0]
    assert command[:2] == [str(utility), str(source)]
    assert command[3:] == [
        "-d",
        "oidn",
        "-a",
        "basecolor",
        "-n",
        "hitN",
        "--aovs",
        "diffuse",
        "indirectDiffuse",
        "--oidn-cpu",
    ]
    assert options["shell"] is False and options["timeout"] == 120
    assert source.read_bytes() == original
    assert context["source_unchanged"] is True
    assert context["dimensions"] == [64, 32]
    assert context["pixel_decode_verified"] is False
    assert context["output_identity"]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert not list(target.parent.glob(".dcc-mcp-denoise-*"))


@pytest.mark.parametrize("same_source", [False, True])
def test_existing_output_and_in_place_are_refused_before_launch(operation, monkeypatch, same_source):
    module, source, target, _ = operation
    if same_source:
        target = source
    else:
        target.write_bytes(b"user-owned final")
    before = target.read_bytes()
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("must not launch"))
    result = module.denoise_image(str(source), str(target))
    assert not result["success"]
    assert target.read_bytes() == before


def test_competing_final_is_not_replaced(operation, monkeypatch):
    module, source, target, _ = operation

    def run(command, **kwargs):
        target.write_bytes(b"concurrently published final")
        return _run_success(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.denoise_image(str(source), str(target))
    assert not result["success"]
    assert target.read_bytes() == b"concurrently published final"


@pytest.mark.parametrize("failure", ["nonzero", "timeout", "empty", "wrong_size", "changed_source"])
def test_failed_operations_do_not_publish(operation, monkeypatch, failure):
    module, source, target, _ = operation
    original = source.read_bytes()

    def run(command, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if failure == "nonzero":
            kwargs["stdout"].write(b"unsupported denoiser or missing AOV")
            return SimpleNamespace(returncode=1)
        if failure == "wrong_size":
            Path(command[2]).write_bytes(_header(width=32))
        elif failure == "changed_source":
            _run_success(command, **kwargs)
            source.write_bytes(original + b"concurrent edit")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.denoise_image(str(source), str(target))
    assert not result["success"], result
    assert not target.exists()
    assert not list(target.parent.glob(".dcc-mcp-denoise-*"))
    if failure != "changed_source":
        assert source.read_bytes() == original


@pytest.mark.parametrize(
    "options",
    [
        {"denoiser": "custom"},
        {"denoiser": "optix", "force_cpu": True},
        {"force_cpu": "true"},
        {"timeout_secs": 301},
        {"timeout_secs": True},
        {"albedo_plane": "--options"},
        {"normal_plane": "N;exit"},
        {"aovs": "C"},
        {"aovs": []},
        {"aovs": ["C"] * 9},
        {"aovs": [None]},
        {"aovs": ["C Cf"]},
    ],
)
def test_invalid_options_are_rejected_before_launch(operation, monkeypatch, options):
    module, source, target, _ = operation
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("must not launch"))
    assert not module.denoise_image(str(source), str(target), **options)["success"]
    assert not target.exists()


@pytest.mark.parametrize(
    "payload",
    [
        b"not an EXR",
        _header(width=0),
        _header(width=8193),
        _header(width=8192, height=8192),
        _header(version=2 | 0x1000),
        _header(payload=b""),
    ],
)
def test_invalid_or_unbounded_input_headers_are_rejected(operation, monkeypatch, payload):
    module, source, target, _ = operation
    source.write_bytes(payload)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("must not launch"))
    result = module.denoise_image(str(source), str(target))
    assert not result["success"]
    assert source.read_bytes() == payload


def test_missing_host_binary_does_not_fall_back_to_path(operation, monkeypatch):
    module, source, target, utility = operation
    utility.unlink()
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("must not launch"))
    result = module.denoise_image(str(source), str(target))
    assert not result["success"]
    assert "HFS/bin" in skill_error_detail(result)


def test_symlinked_source_is_rejected(operation, monkeypatch):
    module, source, target, _ = operation
    alias = source.parent / "alias.exr"
    try:
        alias.symlink_to(source)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("must not launch"))
    assert not module.denoise_image(str(alias), str(target))["success"]


def test_catalog_load_and_dispatch_execute_the_declared_tool(operation, monkeypatch):
    import dcc_mcp_core
    from dcc_mcp_core._server.inprocess_executor import build_inprocess_executor

    _, source, target, _ = operation
    monkeypatch.setattr(subprocess, "run", _run_success)
    registry = dcc_mcp_core.ToolRegistry()
    catalog = dcc_mcp_core.SkillCatalog(registry)
    catalog.set_in_process_executor(build_inprocess_executor(None))
    catalog.discover(extra_paths=[str(_SKILL.parent)], dcc_name="houdini")
    assert "houdini_render__denoise_image" in catalog.load_skill("houdini-render")
    tool = next(tool for tool in catalog.get_skill("houdini-render").tools if tool.name == "denoise_image")
    executor = build_inprocess_executor(None)
    dispatcher = dcc_mcp_core.ToolDispatcher(registry)
    dispatcher.register_handler(
        "houdini_render__denoise_image",
        lambda params: executor(str(_SKILL / tool.source_file), params, thread_affinity="any"),
    )
    result = dispatcher.dispatch(
        "houdini_render__denoise_image", json.dumps({"input_path": str(source), "output_path": str(target)})
    )
    result = result["output"]
    assert result["success"], result
    assert target.is_file()
    assert result["context"]["pixel_decode_verified"] is False
