"""Minimal-mode skill loading configuration for Houdini."""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

from dcc_mcp_core import MinimalModeConfig

# Skills loaded eagerly at startup when minimal mode is enabled.
MINIMAL_SKILLS: Tuple[str, ...] = ("houdini-scripting", "houdini-scene")

# Progressive disclosure stages (see skills/SKILLS_INDEX.md).
STAGES: Tuple[str, ...] = (
    "bootstrap",
    "scene",
    "authoring",
    "interchange",
    "pipeline",
)

# Map stage → bundled skill names (extend as new skills land).
STAGE_SKILLS: dict[str, Tuple[str, ...]] = {
    "bootstrap": ("houdini-scripting",),
    "scene": ("houdini-scene",),
    "authoring": ("houdini-nodes", "houdini-materials", "houdini-hda"),
    "interchange": (),
    "pipeline": ("houdini-pipeline", "houdini-automation"),
}


def skills_for_stage(stage: str) -> Tuple[str, ...]:
    """Return bundled skill names for a stage label."""
    return STAGE_SKILLS.get(stage, ())


def build_minimal_mode_config(
    skill_names: Optional[Iterable[str]] = None,
) -> MinimalModeConfig:
    """Build the default Houdini minimal-mode descriptor."""
    skills = tuple(skill_names) if skill_names is not None else MINIMAL_SKILLS
    return MinimalModeConfig(skills=skills, deactivate_groups=())


def build_minimal_mode_for_stages(stages: Iterable[str]) -> MinimalModeConfig:
    """Build minimal mode that pre-loads every skill in the given stages."""
    names: list[str] = []
    seen: set[str] = set()
    for stage in stages:
        for skill in skills_for_stage(stage):
            if skill not in seen:
                seen.add(skill)
                names.append(skill)
    # bootstrap is always required for execute_python escape hatch.
    for skill in STAGE_SKILLS.get("bootstrap", ()):
        if skill not in seen:
            names.insert(0, skill)
    return MinimalModeConfig(skills=tuple(names), deactivate_groups=())
