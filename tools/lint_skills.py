"""Validate bundled Houdini skills against the current dcc-mcp-core contract."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import List, Optional

import yaml

try:  # dcc-mcp-core is a runtime dep, but keep the structural linter usable without it
    from dcc_mcp_core import validate_skill
except ImportError:  # pragma: no cover - exercised only in lean (prek) environments
    validate_skill = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SKILLS_DIR = ROOT / "src" / "dcc_mcp_houdini" / "skills"

REQUIRED_FIELDS = {"name", "description", "metadata"}
REQUIRED_DCC_MCP_FIELDS = {"dcc", "layer", "version", "tags", "search-hint", "tools"}
REQUIRED_TOOL_FIELDS = {
    "name",
    "description",
    "source_file",
    "execution",
    "affinity",
    "input_schema",
    "read_only",
    "destructive",
    "idempotent",
}
VALID_EXECUTION = {"sync", "async"}
VALID_AFFINITY = {"main", "any"}
SAFETY_FIELDS = {"read_only", "destructive", "idempotent"}


def _find_dcc_mcp_cli() -> Optional[str]:
    exe = shutil.which("dcc-mcp-cli")
    if exe:
        return exe
    if sys.platform == "win32":
        candidate = pathlib.Path.home() / "AppData" / "Local" / "dcc-mcp" / "bin" / "dcc-mcp-cli.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def lint_skills_with_cli(skills_dir: pathlib.Path, warnings_as_errors: bool = False) -> Optional[List[str]]:
    """Run the standalone dcc-mcp-cli linter when it is installed."""
    cli = _find_dcc_mcp_cli()
    if cli is None:
        return None

    cmd = [cli, "lint"]
    if warnings_as_errors:
        cmd.append("--warnings-as-errors")
    cmd.append(str(skills_dir))
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False, capture_output=True, text=True)
    output = (proc.stdout or proc.stderr).strip()
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        return (
            [output or "dcc-mcp-cli lint failed with exit code {}".format(proc.returncode)] if proc.returncode else []
        )

    errors: List[str] = []
    for report in payload.get("reports", []):
        for issue in report.get("issues", []):
            severity = issue.get("severity", "unknown")
            if severity == "error" or warnings_as_errors:
                errors.append("{}: {}: {}".format(report.get("skill_dir"), issue.get("category"), issue.get("message")))

    if proc.returncode != 0 and not errors:
        errors.append(output or "dcc-mcp-cli lint failed with exit code {}".format(proc.returncode))
    return errors


def _parse_front_matter(text: str) -> dict:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        return {}
    return yaml.safe_load("\n".join(lines[1:end])) or {}


def lint_skills(
    skills_dir: pathlib.Path = DEFAULT_SKILLS_DIR,
    *,
    use_cli: bool = True,
    warnings_as_errors: bool = False,
) -> List[str]:
    """Return validation errors for all bundled skill directories.

    The generic SKILL.md / tools.yaml contract is validated by dcc-mcp-core,
    which is the authoritative source of truth. Precision order:

    1. ``dcc-mcp-cli lint`` — the standalone binary; matches the runtime loader
       exactly and is the most precise (preferred locally).
    2. ``dcc_mcp_core.validate_skill`` — the same Rust validator exposed through
       the Python API (used in CI, where the wheel is installed but the CLI
       binary is not).
    3. Built-in structural heuristics — last-resort fallback when neither
       dcc-mcp-cli nor dcc-mcp-core is importable (lean prek environments).

    On top of whichever generic validator runs, Houdini-specific conventions
    (lazy ``hou`` import, ``scripts/`` layout) are always enforced.
    """
    errors: List[str] = []

    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
    if not skill_dirs:
        return ["No skill directories found under {}".format(skills_dir)]

    cli_errors = lint_skills_with_cli(skills_dir, warnings_as_errors=warnings_as_errors) if use_cli else None
    if cli_errors is not None:
        generic_mode = "cli"
        errors.extend(cli_errors)
    elif validate_skill is not None:
        generic_mode = "core"
    else:
        generic_mode = "builtin"
        print(
            "notice: dcc-mcp-cli and dcc-mcp-core are both unavailable; "
            "ran built-in structural checks only (install dcc-mcp-core for precise validation)",
            file=sys.stderr,
        )

    for skill_dir in sorted(skill_dirs):
        _lint_skill_dir(skill_dir, errors, generic_mode=generic_mode)

    return errors


def _lint_skill_dir(skill_dir: pathlib.Path, errors: List[str], *, generic_mode: str) -> None:
    name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        # The CLI already reports missing SKILL.md; only surface it ourselves otherwise.
        if generic_mode != "cli":
            errors.append("{}: missing SKILL.md".format(name))
        return

    try:
        front = _parse_front_matter(skill_md.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        if generic_mode != "cli":
            errors.append("{}: YAML parse error: {}".format(name, exc))
        return

    if not front:
        if generic_mode != "cli":
            errors.append("{}: empty or missing front matter".format(name))
        return

    # Generic contract validation — delegate to dcc-mcp-core when possible.
    if generic_mode == "core":
        report = validate_skill(str(skill_dir))
        if report.has_errors:
            for issue in report.issues:
                errors.append("{}: {}: {}".format(name, issue.category, issue.message))
    elif generic_mode == "builtin":
        _lint_builtin_contract(skill_dir, front, errors)

    # Houdini-specific conventions always run, regardless of the generic validator.
    _lint_houdini_conventions(skill_dir, front, errors)


def _lint_builtin_contract(skill_dir: pathlib.Path, front: dict, errors: List[str]) -> None:
    """Last-resort structural checks used only when dcc-mcp-core is unavailable."""
    name = skill_dir.name
    missing = REQUIRED_FIELDS - set(front.keys())
    if missing:
        errors.append("{}: missing fields: {}".format(name, sorted(missing)))

    dcc_mcp = front.get("metadata", {}).get("dcc-mcp", {})
    missing_dcc_mcp = REQUIRED_DCC_MCP_FIELDS - set(dcc_mcp.keys())
    if missing_dcc_mcp:
        errors.append("{}: missing metadata.dcc-mcp fields: {}".format(name, sorted(missing_dcc_mcp)))
        return

    tools_file = skill_dir / str(dcc_mcp.get("tools", ""))
    if not tools_file.exists():
        errors.append("{}: tools file not found: {}".format(name, dcc_mcp.get("tools")))
        return

    try:
        tools_doc = yaml.safe_load(tools_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        errors.append("{}: tools YAML parse error: {}".format(name, exc))
        return

    tools = tools_doc.get("tools", [])
    if not isinstance(tools, list) or not tools:
        errors.append("{}: tools file must contain a non-empty 'tools' list".format(name))
        return

    for tool in tools:
        _lint_tool_contract(skill_dir, tool, errors)


def _load_tools(skill_dir: pathlib.Path, front: dict) -> List[dict]:
    """Best-effort load of the tools.yaml list; returns [] on any problem."""
    dcc_mcp = front.get("metadata", {}).get("dcc-mcp", {})
    tools_file = skill_dir / str(dcc_mcp.get("tools", ""))
    if not tools_file.exists():
        return []
    try:
        tools_doc = yaml.safe_load(tools_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    tools = tools_doc.get("tools", [])
    return tools if isinstance(tools, list) else []


def _lint_tool_contract(skill_dir: pathlib.Path, tool: dict, errors: List[str]) -> None:
    tool_name = tool.get("name", "?")
    missing_tool = REQUIRED_TOOL_FIELDS - set(tool.keys())
    if missing_tool:
        errors.append("{}/{}: missing tool fields: {}".format(skill_dir.name, tool_name, sorted(missing_tool)))

    execution = tool.get("execution")
    if execution is not None and execution not in VALID_EXECUTION:
        errors.append("{}/{}: invalid execution {!r}".format(skill_dir.name, tool_name, execution))

    affinity = tool.get("affinity")
    if affinity is not None and affinity not in VALID_AFFINITY:
        errors.append("{}/{}: invalid affinity {!r}".format(skill_dir.name, tool_name, affinity))

    for field in SAFETY_FIELDS:
        if field in tool and not isinstance(tool[field], bool):
            errors.append("{}/{}: {} must be a boolean".format(skill_dir.name, tool_name, field))

    if execution == "async" and "timeout_hint_secs" not in tool:
        errors.append("{}/{}: async tools must declare timeout_hint_secs".format(skill_dir.name, tool_name))

    source_file = tool.get("source_file", "")
    if source_file and pathlib.PurePosixPath(source_file).parts[:1] != ("scripts",):
        errors.append("{}/{}: source_file must be under scripts/: {}".format(skill_dir.name, tool_name, source_file))


def _lint_houdini_conventions(skill_dir: pathlib.Path, front: dict, errors: List[str]) -> None:
    """Houdini-specific rules dcc-mcp-core does not enforce (lazy ``hou`` import)."""
    for tool in _load_tools(skill_dir, front):
        tool_name = tool.get("name", "?")
        source_file = tool.get("source_file", "")
        if not source_file:
            continue
        source = skill_dir / source_file
        if not source.exists():
            continue  # missing source is reported by the generic contract validator

        try:
            script_text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append("{}/{}: could not read source file as UTF-8: {}".format(skill_dir.name, tool_name, exc))
            continue

        for forbidden in ("import hou", "from hou"):
            if any(line.startswith(forbidden) for line in script_text.splitlines()):
                errors.append(
                    "{}/{}: hou import must be lazy inside the tool function".format(skill_dir.name, tool_name)
                )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-dir", type=pathlib.Path, default=DEFAULT_SKILLS_DIR)
    parser.add_argument("--no-cli", action="store_true", help="Use Python validation even when dcc-mcp-cli exists.")
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args(argv)

    errors = lint_skills(
        args.skills_dir,
        use_cli=not args.no_cli,
        warnings_as_errors=args.warnings_as_errors,
    )
    if errors:
        print("SKILL.md validation errors:")
        for error in errors:
            print("  - {}".format(error))
        return 1

    print("All SKILL.md files are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
