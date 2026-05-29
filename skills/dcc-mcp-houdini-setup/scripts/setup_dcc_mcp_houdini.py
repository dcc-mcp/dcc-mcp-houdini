"""Prepare a Houdini hython environment for dcc-mcp-houdini MCP use."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


DEFAULT_DIRECT_URL = "http://127.0.0.1:8765/mcp"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:9765/mcp"


def run(command: List[str], cwd: Optional[Path] = None) -> None:
    print("+ " + " ".join(command))
    subprocess.check_call(command, cwd=str(cwd) if cwd else None)


def _hython_name() -> str:
    return "hython.exe" if os.name == "nt" else "hython"


def _glob_install_roots() -> Iterable[Path]:
    """Yield candidate hython binaries from common Houdini install locations."""
    name = _hython_name()
    if os.name == "nt":
        roots = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramW6432"),
        ]
        for root in roots:
            if not root:
                continue
            sidefx = Path(root) / "Side Effects Software"
            if not sidefx.is_dir():
                continue
            for houdini_dir in sorted(sidefx.glob("Houdini*"), reverse=True):
                yield houdini_dir / "bin" / name
    elif sys.platform == "darwin":
        apps = Path("/Applications/Houdini")
        if apps.is_dir():
            for houdini_dir in sorted(apps.glob("Houdini*"), reverse=True):
                yield houdini_dir / "Frameworks" / "Houdini.framework" / "Versions" / "Current" / "Resources" / "bin" / name
                yield houdini_dir / "bin" / name
    else:
        opt = Path("/opt")
        if opt.is_dir():
            for hfs_dir in sorted(opt.glob("hfs*"), reverse=True):
                yield hfs_dir / "bin" / name


def candidate_hython_paths() -> Iterable[Path]:
    env_value = os.environ.get("HYTHON") or os.environ.get("DCC_MCP_HOUDINI_HYTHON")
    if env_value:
        yield Path(env_value)

    path_match = shutil.which("hython")
    if path_match:
        yield Path(path_match)

    for candidate in _glob_install_roots():
        yield candidate


def resolve_hython(explicit: Optional[str]) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if path.exists():
            return path
        raise SystemExit("hython does not exist: %s" % path)

    seen = set()
    for path in candidate_hython_paths():
        expanded = path.expanduser()
        key = str(expanded).lower()
        if key in seen:
            continue
        seen.add(key)
        if expanded.exists():
            return expanded

    raise SystemExit(
        "Could not find hython. Re-run with --hython, or set HYTHON / "
        "DCC_MCP_HOUDINI_HYTHON to the full path "
        "(for example C:\\Program Files\\Side Effects Software\\Houdini 20.5.487\\bin\\hython.exe)."
    )


def find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists() and (parent / "src" / "dcc_mcp_houdini").exists():
            return parent
    return Path.cwd()


def _extra_exists(repo_root: Path, extra: str) -> bool:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return False
    text = pyproject.read_text(encoding="utf-8")
    return ("\n%s = [" % extra) in text or ("\n%s=[" % extra) in text


def install_package(hython: Path, source: str, repo_root: Path, skip_install: bool) -> None:
    if skip_install:
        print("Skipping pip install because --skip-install was passed.")
        return

    run([str(hython), "-m", "ensurepip", "--upgrade"])
    run(
        [
            str(hython),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip<25; python_version<'3.8'",
            "pip; python_version>='3.8'",
        ]
    )

    if source == "local":
        # dcc-mcp-houdini defines no runtime extra (only a dev extra in
        # pyproject), so install the plain editable checkout. dcc-mcp-core is a
        # hard dependency and is resolved automatically.
        target = "."
        if _extra_exists(repo_root, "sidecar"):
            target = ".[sidecar]"
        run([str(hython), "-m", "pip", "install", "-e", target], cwd=repo_root)
    elif source == "pypi":
        run([str(hython), "-m", "pip", "install", "--upgrade", "dcc-mcp-houdini"])
    else:
        raise SystemExit("Unknown source: %s" % source)


def verify_import(hython: Path) -> None:
    code = (
        "import dcc_mcp_houdini; "
        "print('dcc-mcp-houdini', dcc_mcp_houdini.__version__); "
        "import dcc_mcp_core; "
        "print('dcc-mcp-core import ok')"
    )
    run([str(hython), "-c", code])


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("Wrote %s" % path)


def write_mcp_snippets(out_dir: Path, server_name: str, mcp_url: str) -> None:
    payload = {"mcpServers": {server_name: {"url": mcp_url}}}
    write_json(out_dir / "mcp-streamable-http.json", payload)

    gateway_payload = {"mcpServers": {server_name: {"url": DEFAULT_GATEWAY_URL}}}
    write_json(out_dir / "mcp-gateway-9765.json", gateway_payload)

    smoke_prompt = """Use the Houdini MCP server. First call dcc_capability_manifest with loaded_only=false.
Then load the houdini-nodes skill, create a geo node named mcp_setup_smoke_geo
under /obj, list the obj-level nodes, and tell me the MCP URL and created node path.
Use typed tools where available and avoid execute_python unless no typed tool fits.
"""
    smoke_path = out_dir / "smoke-prompt.txt"
    smoke_path.write_text(smoke_prompt, encoding="utf-8")
    print("Wrote %s" % smoke_path)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hython", help="Full path to Houdini hython.")
    parser.add_argument(
        "--source",
        choices=["local", "pypi"],
        default="local",
        help="Install from this checkout or from PyPI. Default: local.",
    )
    parser.add_argument(
        "--mcp-url",
        default=DEFAULT_DIRECT_URL,
        help="MCP URL to write into generated host config. Default: direct autostart URL.",
    )
    parser.add_argument(
        "--server-name",
        default="houdini",
        help="MCP server name in generated config. Default: houdini.",
    )
    parser.add_argument(
        "--out-dir",
        default=".dcc-mcp/agent-setup",
        help="Directory for generated MCP snippets. Default: .dcc-mcp/agent-setup.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Only verify imports and write MCP snippets.",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    repo_root = find_repo_root()
    hython = resolve_hython(args.hython)
    out_dir = (repo_root / args.out_dir).resolve()

    print("Repository: %s" % repo_root)
    print("hython: %s" % hython)
    print("MCP URL: %s" % args.mcp_url)

    install_package(hython, args.source, repo_root, args.skip_install)
    verify_import(hython)
    write_mcp_snippets(out_dir, args.server_name, args.mcp_url)

    print("")
    print("Next:")
    print("1. Install the Houdini package so 123.py autostart runs (see install.md).")
    print("2. Start Houdini; watch for the 'dcc-mcp-houdini MCP server started' line.")
    print("3. Configure the MCP host with %s." % (out_dir / "mcp-streamable-http.json"))
    print("4. Run the smoke prompt in %s." % (out_dir / "smoke-prompt.txt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
