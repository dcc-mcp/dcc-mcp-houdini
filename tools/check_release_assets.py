"""Fail closed before attaching immutable GitHub release assets."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TAG = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_GH_TIMEOUT_SECONDS = 30


class GuardError(Exception):
    """Stable public failure raised by the release asset guard."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _parse_args(arguments: Sequence[str]) -> Tuple[str, str, List[str]]:
    repository: Optional[str] = None
    tag: Optional[str] = None
    patterns: List[str] = []
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option not in ("--repository", "--tag", "--pattern") or index + 1 >= len(arguments):
            raise GuardError("invalid_arguments")
        value = arguments[index + 1]
        if option == "--repository" and repository is None:
            repository = value
        elif option == "--tag" and tag is None:
            tag = value
        elif option == "--pattern":
            patterns.append(value)
        else:
            raise GuardError("invalid_arguments")
        index += 2

    if repository is None or _REPOSITORY.fullmatch(repository) is None:
        raise GuardError("invalid_repository")
    if tag is None or _TAG.fullmatch(tag) is None:
        raise GuardError("invalid_tag")
    if not patterns:
        raise GuardError("invalid_artifact_pattern")
    return repository, tag, patterns


def _validate_pattern(pattern: str) -> None:
    portable = pattern.replace("\\", "/")
    parts = PurePosixPath(portable).parts
    if not pattern or portable.startswith("/") or _WINDOWS_DRIVE.match(portable) or ".." in parts:
        raise GuardError("invalid_artifact_pattern")


def _artifact_basenames(patterns: Sequence[str], cwd: Path) -> Set[str]:
    basenames: List[str] = []
    for pattern in patterns:
        _validate_pattern(pattern)
        matched = sorted(Path(value) for value in glob.glob(str(cwd / pattern)))
        if not matched:
            raise GuardError("artifact_pattern_unmatched")
        if any(path.is_symlink() or not path.is_file() for path in matched):
            raise GuardError("artifact_not_regular")
        basenames.extend(path.name for path in matched)

    if len(basenames) != len(set(basenames)):
        raise GuardError("duplicate_artifact_basename")
    return set(basenames)


def _github_pages(
    endpoint: str,
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess],
) -> List[List[Dict[str, Any]]]:
    child_env = dict(environ)
    child_env["GH_HOST"] = "github.com"
    command = [
        "gh",
        "api",
        "--hostname",
        "github.com",
        "--paginate",
        "--slurp",
        endpoint,
    ]
    try:
        completed = runner(
            command,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise GuardError("github_api_unavailable") from None
    if completed.returncode != 0:
        raise GuardError("github_api_unavailable")
    try:
        pages = json.loads(completed.stdout)
    except (TypeError, ValueError):
        raise GuardError("github_api_invalid_response") from None
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise GuardError("github_api_invalid_response")
    if any(not isinstance(item, dict) for page in pages for item in page):
        raise GuardError("github_api_invalid_response")
    return pages


def _existing_asset_names(
    repository: str,
    tag: str,
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess],
) -> Set[str]:
    release_pages = _github_pages("repos/{}/releases?per_page=100".format(repository), environ, runner)
    matching = [item for page in release_pages for item in page if item.get("tag_name") == tag]
    if not matching:
        return set()
    if len(matching) != 1:
        raise GuardError("github_api_invalid_response")
    release_id = matching[0].get("id")
    if isinstance(release_id, bool) or not isinstance(release_id, int) or release_id <= 0:
        raise GuardError("github_api_invalid_response")

    asset_pages = _github_pages(
        "repos/{}/releases/{}/assets?per_page=100".format(repository, release_id), environ, runner
    )
    names: Set[str] = set()
    for page in asset_pages:
        for asset in page:
            name = asset.get("name")
            if not isinstance(name, str) or not name:
                raise GuardError("github_api_invalid_response")
            names.add(name)
    return names


def main(
    arguments: Optional[Sequence[str]] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> int:
    """Validate local artifacts and refuse exact-name release collisions."""

    try:
        repository, tag, patterns = _parse_args(list(arguments if arguments is not None else sys.argv[1:]))
        environment = dict(environ if environ is not None else os.environ)
        artifact_names = _artifact_basenames(patterns, cwd if cwd is not None else Path.cwd())
        if not environment.get("GH_TOKEN"):
            raise GuardError("github_token_missing")
        existing_names = _existing_asset_names(repository, tag, environment, runner)
        if artifact_names.intersection(existing_names):
            raise GuardError("asset_name_collision")
    except GuardError as exc:
        sys.stderr.write("release asset guard failed: {}\n".format(exc.code))
        return 1
    except Exception:
        sys.stderr.write("release asset guard failed: internal_error\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
