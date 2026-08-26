"""Executable tests for immutable GitHub release asset uploads."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_release_assets.py"


class _FakeGh:
    def __init__(self, *responses: Tuple[int, str, str]) -> None:
        self.responses = list(responses)
        self.calls: List[Tuple[List[str], Dict[str, Any]]] = []

    def __call__(self, command: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append((command, kwargs))
        returncode, stdout, stderr = self.responses.pop(0)
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def _load_guard() -> Any:
    assert SCRIPT.is_file(), "release asset guard script is missing"
    spec = importlib.util.spec_from_file_location("release_asset_guard", str(SCRIPT))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(
    tmp_path: Path,
    fake: _FakeGh,
    patterns: Optional[List[str]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> int:
    module = _load_guard()
    arguments = ["--repository", "dcc-mcp/dcc-mcp-houdini", "--tag", "v1.2.3"]
    for pattern in patterns or ["dist/*"]:
        arguments.extend(["--pattern", pattern])
    environment = {"GH_TOKEN": "PRIVATE_TOKEN_71aa", "GH_HOST": "private.invalid"}
    if environ:
        environment.update(environ)
    return module.main(arguments, environ=environment, cwd=tmp_path, runner=fake)


def test_missing_artifact_pattern_fails_before_github_io(tmp_path: Path, capsys: Any) -> None:
    fake = _FakeGh()

    assert _run(tmp_path, fake) == 1
    assert fake.calls == []
    assert capsys.readouterr().err == "release asset guard failed: artifact_pattern_unmatched\n"


def test_duplicate_local_basenames_fail_before_github_io(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "quick").mkdir()
    (tmp_path / "dist" / "same.zip").write_bytes(b"wheel")
    (tmp_path / "quick" / "same.zip").write_bytes(b"quickinstall")
    fake = _FakeGh()

    assert _run(tmp_path, fake, ["dist/*", "quick/*"]) == 1
    assert fake.calls == []
    assert capsys.readouterr().err == "release asset guard failed: duplicate_artifact_basename\n"


def test_local_raw_and_aligned_identity_overlap_fails_before_github_io(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "artifact name.whl").write_bytes(b"first")
    (tmp_path / "dist" / "artifact.name.whl").write_bytes(b"second")
    fake = _FakeGh((0, json.dumps([[]]), ""))

    assert _run(tmp_path, fake) == 1
    assert fake.calls == []
    assert capsys.readouterr().err == "release asset guard failed: duplicate_artifact_identity\n"


def test_missing_release_allows_new_unicode_assets_and_forces_github_host(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "dcc_houdini_资产.zip").write_bytes(b"asset")
    fake = _FakeGh((0, json.dumps([[]]), ""))

    assert _run(tmp_path, fake) == 0
    assert capsys.readouterr().err == ""
    assert len(fake.calls) == 1
    command, kwargs = fake.calls[0]
    assert command == [
        "gh",
        "api",
        "--hostname",
        "github.com",
        "--paginate",
        "--slurp",
        "repos/dcc-mcp/dcc-mcp-houdini/releases?per_page=100",
    ]
    assert kwargs["env"]["GH_HOST"] == "github.com"
    assert kwargs["env"]["GH_TOKEN"] == "PRIVATE_TOKEN_71aa"


def test_paginated_exact_collision_fails_without_leaking_hostile_values(tmp_path: Path, capsys: Any) -> None:
    hostile_name = "私密-REVIEW_SECRET_7f0a.zip"
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / hostile_name).write_bytes(b"asset")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 1, "tag_name": "v0.9.0"}], [{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "unrelated.whl"}], [{"name": hostile_name}]]), ""),
    )

    assert _run(tmp_path, fake) == 1
    error = capsys.readouterr().err
    assert error == "release asset guard failed: asset_name_collision\n"
    assert hostile_name not in error
    assert "PRIVATE_TOKEN_71aa" not in error
    assert str(tmp_path) not in error
    assert fake.calls[1][0][-1] == "repos/dcc-mcp/dcc-mcp-houdini/releases/77/assets?per_page=100"


def test_remote_aligned_name_collision_is_rejected(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "artifact name.whl").write_bytes(b"wheel")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "artifact.name.whl", "label": None}]]), ""),
    )

    assert _run(tmp_path, fake) == 1
    assert capsys.readouterr().err == "release asset guard failed: asset_name_collision\n"


def test_alignment_replaces_each_ascii_space_without_changing_unicode(tmp_path: Path, capsys: Any) -> None:
    local_name = "资产  build.whl"
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / local_name).write_bytes(b"wheel")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "资产..build.whl"}]]), ""),
    )

    assert _run(tmp_path, fake) == 1
    error = capsys.readouterr().err
    assert error == "release asset guard failed: asset_name_collision\n"
    assert local_name not in error


def test_remote_label_collision_is_rejected_when_github_rewrote_the_name(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "artifact.whl").write_bytes(b"wheel")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "rewritten.whl", "label": "artifact.whl"}]]), ""),
    )

    assert _run(tmp_path, fake) == 1
    assert capsys.readouterr().err == "release asset guard failed: asset_name_collision\n"


def test_remote_label_is_not_over_normalized(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "artifact name.whl").write_bytes(b"wheel")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "unrelated.whl", "label": "artifact.name.whl"}]]), ""),
    )

    assert _run(tmp_path, fake) == 0
    assert capsys.readouterr().err == ""


def test_unrelated_existing_assets_allow_upload(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "new.whl").write_bytes(b"wheel")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "old.whl"}, {"name": "旧.zip"}]]), ""),
    )

    assert _run(tmp_path, fake) == 0
    assert capsys.readouterr().err == ""


def test_already_dotted_local_name_does_not_collide_with_itself(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "already.dotted.whl").write_bytes(b"wheel")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "unrelated.whl", "label": None}]]), ""),
    )

    assert _run(tmp_path, fake) == 0
    assert capsys.readouterr().err == ""


def test_github_api_failure_is_fail_closed_and_redacted(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "new.whl").write_bytes(b"wheel")
    fake = _FakeGh((1, "", "PRIVATE_TOKEN_71aa /private/release/path"))

    assert _run(tmp_path, fake) == 1
    error = capsys.readouterr().err
    assert error == "release asset guard failed: github_api_unavailable\n"
    assert "PRIVATE_TOKEN_71aa" not in error
    assert "/private/release/path" not in error


def test_empty_pattern_and_malformed_api_payload_fail_closed(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "new.whl").write_bytes(b"wheel")

    assert _run(tmp_path, _FakeGh(), [""]) == 1
    assert capsys.readouterr().err == "release asset guard failed: invalid_artifact_pattern\n"

    fake = _FakeGh((0, "{not-json", ""))
    assert _run(tmp_path, fake) == 1
    assert capsys.readouterr().err == "release asset guard failed: github_api_invalid_response\n"


def test_non_string_remote_label_fails_closed(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "artifact.whl").write_bytes(b"wheel")
    fake = _FakeGh(
        (0, json.dumps([[{"id": 77, "tag_name": "v1.2.3"}]]), ""),
        (0, json.dumps([[{"name": "unrelated.whl", "label": 7}]]), ""),
    )

    assert _run(tmp_path, fake) == 1
    assert capsys.readouterr().err == "release asset guard failed: github_api_invalid_response\n"


def test_script_cli_rejects_missing_glob_with_stable_error(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repository",
            "dcc-mcp/dcc-mcp-houdini",
            "--tag",
            "v1.2.3",
            "--pattern",
            "dist/*",
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "release asset guard failed: artifact_pattern_unmatched\n"
