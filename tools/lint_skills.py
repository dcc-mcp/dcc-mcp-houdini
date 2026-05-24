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
from dcc_mcp_core import validate_skill

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
    """Return validation errors for all bundled skill directories."""
    errors: List[str] = []
    if use_cli:
        cli_errors = lint_skills_with_cli(skills_dir, warnings_as_errors=warnings_as_errors)
        if cli_errors is not None:
            errors.extend(cli_errors)

    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
    if not skill_dirs:
        return ["No skill directories found under {}".format(skills_dir)]

    for skill_dir in sorted(skill_dirs):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append("{}: missing SKILL.md".format(skill_dir.name))
            continue

        try:
            front = _parse_front_matter(skill_md.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append("{}: YAML parse error: {}".format(skill_dir.name, exc))
            continue

        if not front:
            errors.append("{}: empty or missing front matter".format(skill_dir.name))
            continue

        report = validate_skill(str(skill_dir))
        if report.has_errors:
            for issue in report.issues:
                errors.append("{}: {}: {}".format(skill_dir.name, issue.category, issue.message))

        missing = REQUIRED_FIELDS - set(front.keys())
        if missing:
            errors.append("{}: missing fields: {}".format(skill_dir.name, sorted(missing)))

        dcc_mcp = front.get("metadata", {}).get("dcc-mcp", {})
        missing_dcc_mcp = REQUIRED_DCC_MCP_FIELDS - set(dcc_mcp.keys())
        if missing_dcc_mcp:
            errors.append("{}: missing metadata.dcc-mcp fields: {}".format(skill_dir.name, sorted(missing_dcc_mcp)))
            continue

        tools_file = skill_dir / str(dcc_mcp.get("tools", ""))
        if not tools_file.exists():
            errors.append("{}: tools file not found: {}".format(skill_dir.name, dcc_mcp.get("tools")))
            continue

        try:
            tools_doc = yaml.safe_load(tools_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            errors.append("{}: tools YAML parse error: {}".format(skill_dir.name, exc))
            continue

        tools = tools_doc.get("tools", [])
        if not isinstance(tools, list) or not tools:
            errors.append("{}: tools file must contain a non-empty 'tools' list".format(skill_dir.name))
            continue

        for tool in tools:
            _lint_tool(skill_dir, tool, errors)

    return errors


def _lint_tool(skill_dir: pathlib.Path, tool: dict, errors: List[str]) -> None:
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

    source = skill_dir / source_file
    if not source.exists():
        errors.append("{}: source_file not found: {}".format(skill_dir.name, source_file))
        return

    try:
        script_text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append("{}/{}: could not read source file as UTF-8: {}".format(skill_dir.name, tool_name, exc))
        return

    for forbidden in ("import hou", "from hou"):
        if any(line.startswith(forbidden) for line in script_text.splitlines()):
            errors.append("{}/{}: hou import must be lazy inside the tool function".format(skill_dir.name, tool_name))


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
