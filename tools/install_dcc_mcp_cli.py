"""Download the standalone ``dcc-mcp-cli`` binary from dcc-mcp-core releases.

The skill linter (:mod:`tools.lint_skills`) prefers the standalone
``dcc-mcp-cli`` binary because it is the exact validator the runtime skill
loader uses. The binary is published as a per-platform asset on the
``loonghao/dcc-mcp-core`` GitHub releases, so CI and contributors can fetch it
with nothing more than the Python standard library.

Usage::

    python tools/install_dcc_mcp_cli.py                 # latest release -> ./.tools-bin
    python tools/install_dcc_mcp_cli.py --tag v0.17.47  # pin a release
    python tools/install_dcc_mcp_cli.py --install-dir /usr/local/bin

When ``GITHUB_PATH`` is set (i.e. inside GitHub Actions) the install directory
is appended to it automatically so later steps find the binary on ``PATH``.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import stat
import sys
import urllib.error
import urllib.request
from typing import Optional

REPO = "dcc-mcp/dcc-mcp-core"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_INSTALL_DIR = ROOT / ".tools-bin"


def _asset_name() -> str:
    """Return the release asset name for the current platform."""
    platform = sys.platform
    if platform == "win32":
        return "dcc-mcp-cli-windows-x86_64.exe"
    if platform == "darwin":
        return "dcc-mcp-cli-macos-universal2"
    if platform.startswith("linux"):
        return "dcc-mcp-cli-linux-x86_64"
    raise SystemExit(f"unsupported platform: {platform!r}")


def _binary_name() -> str:
    return "dcc-mcp-cli.exe" if sys.platform == "win32" else "dcc-mcp-cli"


def _request(url: str) -> urllib.request.Request:
    headers = {"Accept": "application/json", "User-Agent": "dcc-mcp-houdini-installer"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _release_api_url(tag: Optional[str]) -> str:
    if tag:
        return f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"
    return f"https://api.github.com/repos/{REPO}/releases/latest"


def _resolve_download_url(tag: Optional[str], asset_name: str) -> str:
    api_url = _release_api_url(tag)
    try:
        with urllib.request.urlopen(_request(api_url), timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failure path
        raise SystemExit(f"failed to query {api_url}: HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network failure path
        raise SystemExit(f"failed to query {api_url}: {exc.reason}") from exc

    for asset in payload.get("assets", []):
        if asset.get("name") == asset_name:
            return asset["browser_download_url"]

    available = ", ".join(sorted(a.get("name", "?") for a in payload.get("assets", [])))
    raise SystemExit(f"asset {asset_name!r} not found in release {payload.get('tag_name')!r}. available: {available}")


def _download(url: str, dest: pathlib.Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(_request(url), timeout=300) as resp, tmp.open("wb") as fh:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:  # pragma: no cover - network failure path
        raise SystemExit(f"failed to download {url}: {exc}") from exc
    tmp.replace(dest)


def _make_executable(path: pathlib.Path) -> None:
    if sys.platform == "win32":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _export_to_github_path(install_dir: pathlib.Path) -> None:
    github_path = os.environ.get("GITHUB_PATH")
    if not github_path:
        return
    with open(github_path, "a", encoding="utf-8") as fh:
        fh.write(str(install_dir) + "\n")
    print(f"added {install_dir} to GITHUB_PATH")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="Release tag to pin (default: latest release).")
    parser.add_argument(
        "--install-dir",
        type=pathlib.Path,
        default=DEFAULT_INSTALL_DIR,
        help=f"Directory to install the binary into (default: {DEFAULT_INSTALL_DIR}).",
    )
    args = parser.parse_args(argv)

    asset_name = _asset_name()
    dest = args.install_dir / _binary_name()

    url = _resolve_download_url(args.tag, asset_name)
    print(f"downloading {asset_name} -> {dest}")
    _download(url, dest)
    _make_executable(dest)
    _export_to_github_path(args.install_dir)

    print(f"installed dcc-mcp-cli at {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
