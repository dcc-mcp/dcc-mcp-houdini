"""Emit or validate a structured character design spec (the "codex" step).

This is the deterministic in-adapter equivalent of asking an external LLM
(codex) to design a character. Instead of free-form prose, it produces a
strict JSON contract that downstream tools (biped template, retarget, capture,
ragdoll, APEX FBX) can consume. An external LLM can author the same schema and
``design_character`` will validate it, so the workflow works both online and
offline without the external capability.

Pure tool: no ``hou`` import; safe to run headless and fully unit-testable.
"""

from __future__ import annotations

from typing import Any, Optional

from _character_common import CONVENTIONS, convention_names
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

SPEC_SCHEMA = "dcc-mcp-houdini.character-design/v1"

STYLE_PRESETS = {
    "realistic": {"proportions": "realistic", "finger_detail": True, "face_rig": True},
    "stylized": {"proportions": "stylized", "finger_detail": True, "face_rig": False},
    "cartoon": {"proportions": "exaggerated", "finger_detail": False, "face_rig": True},
    "stylized_game": {"proportions": "heroic", "finger_detail": True, "face_rig": False},
}

DEFAULT_SPEC = {
    "schema": SPEC_SCHEMA,
    "name": "hero",
    "style": "stylized_game",
    "engine": "unreal",
    "units": "meters",
    "target_height": 1.7,
    "naming_convention": "kinefx",
    "face_forward": "+Z",
    "up_axis": "Y",
    "skeleton": {"template": "humanoid_biped", "joint_count": 22},
    "features": {
        "fingers": True,
        "face_rig": False,
        "twist_bones": True,
        "props": [],
    },
    "pipeline": {
        "capture_method": "proximity",
        "retarget_source_convention": "mixamo",
        "full_body_ik": True,
        "ragdoll": True,
        "apex_fbx_biped": True,
    },
}

# Fields an externally-authored (e.g. codex) spec must provide and their types.
REQUIRED_FIELDS = {
    "name": str,
    "target_height": (int, float),
    "naming_convention": str,
}


def _build_spec(
    name: str,
    style: str,
    engine: str,
    height: float,
    convention: str,
    face_forward: str,
    up_axis: str,
) -> dict:
    spec = {key: (dict(value) if isinstance(value, dict) else value) for key, value in DEFAULT_SPEC.items()}
    spec["name"] = name
    spec["style"] = style
    spec["engine"] = engine
    spec["units"] = "meters"
    spec["target_height"] = float(height)
    spec["naming_convention"] = convention
    spec["face_forward"] = face_forward
    spec["up_axis"] = up_axis
    spec["style_preset"] = dict(STYLE_PRESETS.get(style, STYLE_PRESETS["stylized"]))
    spec["features"]["fingers"] = bool(spec["style_preset"]["finger_detail"])
    spec["features"]["face_rig"] = bool(spec["style_preset"]["face_rig"])
    spec["skeleton"]["naming"] = convention_names(convention)
    return spec


def _validate_spec(spec: Any) -> list:
    """Return a list of validation error strings (empty when valid)."""
    errors = []
    if not isinstance(spec, dict):
        return ["design spec must be an object"]
    for field, expected in REQUIRED_FIELDS.items():
        if field not in spec:
            errors.append("missing required field: {}".format(field))
        elif not isinstance(spec[field], expected):
            errors.append("field {} must be {}".format(field, expected))
    if "naming_convention" in spec and spec["naming_convention"] not in CONVENTIONS:
        errors.append("naming_convention must be one of {}".format(", ".join(CONVENTIONS)))
    if "target_height" in spec and isinstance(spec["target_height"], (int, float)):
        if spec["target_height"] <= 0:
            errors.append("target_height must be positive")
    if "up_axis" in spec and spec["up_axis"] not in ("Y", "Z"):
        errors.append("up_axis must be 'Y' or 'Z'")
    return errors


def design_character(
    name: str = "hero",
    style: str = "stylized_game",
    engine: str = "unreal",
    height: float = 1.7,
    naming_convention: str = "kinefx",
    face_forward: str = "+Z",
    up_axis: str = "Y",
    spec: Optional[dict] = None,
) -> dict:
    """Emit a validated design spec, or validate an externally-authored one.

    When *spec* is provided (e.g. the JSON produced by codex), it is validated
    against the schema and returned with a ``validated`` flag instead of being
    regenerated. Otherwise a deterministic spec is built from the arguments.
    """
    if naming_convention not in CONVENTIONS:
        return skill_error(
            "Unknown naming convention",
            "naming_convention must be one of {}".format(", ".join(CONVENTIONS)),
            naming_convention=naming_convention,
        )
    if style not in STYLE_PRESETS:
        return skill_error(
            "Unknown style",
            "style must be one of {}".format(", ".join(sorted(STYLE_PRESETS))),
            style=style,
        )
    if height <= 0:
        return skill_error("Invalid height", "height must be positive", height=height)

    if spec is not None:
        errors = _validate_spec(spec)
        if errors:
            return skill_error("Invalid design spec", "; ".join(errors), errors=errors)
        return skill_success(
            "Validated external character design spec",
            validated=True,
            source="external",
            design_spec=spec,
            schema=SPEC_SCHEMA,
        )

    built = _build_spec(name, style, engine, height, naming_convention, face_forward, up_axis)
    errors = _validate_spec(built)
    if errors:  # pragma: no cover - defensive guard on the built spec
        return skill_error("Generated spec failed validation", "; ".join(errors), errors=errors)
    return skill_success(
        "Generated character design spec",
        validated=True,
        source="deterministic",
        design_spec=built,
        schema=SPEC_SCHEMA,
    )


@skill_entry
def main(**kwargs) -> dict:
    return design_character(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
