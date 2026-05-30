"""Regression tests for intelligent-recall metadata on bundled skills (#21).

These assert two things:

1. Core can still load every bundled skill with the new metadata present
   (no breakage) and surfaces the skill/tool ``search_aliases`` it supports
   today.
2. The richer recall metadata authored under ``metadata.dcc-mcp.*`` and in
   ``tools.yaml`` is well-formed in the raw frontmatter, so it activates as
   soon as core wires the override arms — regardless of whether the pinned
   core version already reads it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_TRACKED_SKILLS = (
    "houdini-scripting",
    "houdini-scene",
    "houdini-nodes",
    "houdini-materials",
    "houdini-hda",
    "houdini-automation",
)


def _frontmatter(skill_dir: str) -> dict:
    text = (_SKILLS_ROOT / skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---"), skill_dir
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def _recall(skill_dir: str) -> dict:
    return _frontmatter(skill_dir)["metadata"]["dcc-mcp"]


@pytest.mark.parametrize("skill_dir", _TRACKED_SKILLS)
def test_skill_has_search_aliases(skill_dir: str) -> None:
    recall = _recall(skill_dir)
    aliases = recall.get("search-aliases")
    assert isinstance(aliases, list) and aliases, skill_dir


@pytest.mark.parametrize("skill_dir", _TRACKED_SKILLS)
def test_skill_has_recall_context(skill_dir: str) -> None:
    recall = _recall(skill_dir)
    ctx = recall.get("recall-context")
    assert isinstance(ctx, dict), skill_dir
    assert ctx.get("app_type") == "houdini"
    assert ctx.get("workflow-stage")
    assert ctx.get("task-category")


@pytest.mark.parametrize("skill_dir", _TRACKED_SKILLS)
def test_skill_has_intent_and_example_prompts(skill_dir: str) -> None:
    recall = _recall(skill_dir)
    assert recall.get("intent"), skill_dir
    prompts = recall.get("example-prompts")
    assert isinstance(prompts, list) and prompts, skill_dir


def test_scripting_marked_escape_hatch() -> None:
    tools = yaml.safe_load(
        (_SKILLS_ROOT / "houdini-scripting" / "tools.yaml").read_text(encoding="utf-8")
    )["tools"]
    execute = next(t for t in tools if t["name"] == "execute_python")
    assert execute["tool_role"] == "escape_hatch"
    assert execute["risk"] == "host_script_execution"


def test_run_python_file_marked_escape_hatch() -> None:
    tools = yaml.safe_load(
        (_SKILLS_ROOT / "houdini-automation" / "tools.yaml").read_text(encoding="utf-8")
    )["tools"]
    runner = next(t for t in tools if t["name"] == "run_python_file")
    assert runner["tool_role"] == "escape_hatch"


def test_destructive_tools_have_high_risk() -> None:
    nodes = yaml.safe_load(
        (_SKILLS_ROOT / "houdini-nodes" / "tools.yaml").read_text(encoding="utf-8")
    )["tools"]
    delete = next(t for t in nodes if t["name"] == "delete_node")
    assert delete["tool_role"] == "destructive"
    assert delete["risk"] == "high"


def test_every_tool_has_search_aliases() -> None:
    for skill_dir in _TRACKED_SKILLS:
        tools = yaml.safe_load(
            (_SKILLS_ROOT / skill_dir / "tools.yaml").read_text(encoding="utf-8")
        )["tools"]
        for tool in tools:
            aliases = tool.get("search_aliases")
            assert isinstance(aliases, list) and aliases, f"{skill_dir}:{tool['name']}"


def test_core_loads_skills_with_aliases() -> None:
    """Core must load every bundled skill and expose skill-level aliases today."""
    from dcc_mcp_core import scan_and_load

    skills, skipped = scan_and_load(
        dcc_name="houdini", extra_paths=[str(_SKILLS_ROOT)]
    )
    assert not skipped, skipped
    by_name = {s.name: s for s in skills}
    for skill_dir in _TRACKED_SKILLS:
        skill = by_name.get(skill_dir)
        assert skill is not None, skill_dir
        assert list(getattr(skill, "search_aliases", []) or []), skill_dir
