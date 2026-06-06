"""Version floor consistency checks — keep pyproject.toml, packaging script,
and SKILL.md compatibility strings from drifting apart."""

from __future__ import annotations

import re
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PACKAGING_SCRIPT = ROOT / "packaging" / "assemble_houdini_package.py"
SKILLS_DIR = ROOT / "src" / "dcc_mcp_houdini" / "skills"


def _extract_pyproject_core_floor() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'"dcc-mcp-core>=([^,"]+)', text)
    if not m:
        raise RuntimeError("Could not find dcc-mcp-core dependency in pyproject.toml")
    return m.group(1).strip()


def _extract_packaging_min_core_version() -> str:
    text = PACKAGING_SCRIPT.read_text(encoding="utf-8")
    m = re.search(r'MIN_CORE_VERSION\s*=\s*"([^"]+)"', text)
    if not m:
        raise RuntimeError("Could not find MIN_CORE_VERSION in assemble_houdini_package.py")
    return m.group(1).strip()


def test_pyproject_and_packaging_core_floor_match() -> None:
    """pyproject.toml dep floor and packaging MIN_CORE_VERSION must be identical."""
    pyproject_floor = _extract_pyproject_core_floor()
    packaging_floor = _extract_packaging_min_core_version()
    assert pyproject_floor == packaging_floor, (
        f"Mismatch: pyproject.toml requires >= {pyproject_floor}, "
        f"but packaging script pins MIN_CORE_VERSION = {packaging_floor}"
    )


def test_skill_compatibility_runtime_floor() -> None:
    """Every SKILL.md compatibility string must declare dcc-mcp-core >= current floor."""
    expected_floor = Version(_extract_pyproject_core_floor())
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        m = re.search(r"dcc-mcp-core\s+([0-9]+\.[0-9]+\.[0-9]+)", text)
        assert m, f"{skill_md.relative_to(ROOT)}: missing dcc-mcp-core compatibility"
        declared = Version(m.group(1))
        assert declared >= expected_floor, (
            f"{skill_md.relative_to(ROOT)}: declares dcc-mcp-core {declared}, but project floor is >= {expected_floor}"
        )
