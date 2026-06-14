"""Create a blend constraint — blend between multiple target transforms."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _constraint_common import build_blend_node  # noqa: E402


def create_blend_constraint(
    driven_path: str,
    target_paths: List[str],
    weights: Optional[List[float]] = None,
) -> dict:
    """Create a blend constraint between *driven_path* and *target_paths*.

    Each target is wired as an input to a ``blend`` OBJ node, with optional
    per-target weights.  The driven object's transform is expression-linked to
    the blend output, producing a weighted average of the target transforms.

    Args:
        driven_path: Path to the object being constrained.
        target_paths: List of target object paths to blend between.
        weights: Optional per-target weight list (must match target count).
            Default weights are evenly distributed.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if len(target_paths) < 1:
        return skill_error("Need at least one target", "target_paths must not be empty")

    if weights and len(weights) != len(target_paths):
        return skill_error(
            "Weight count mismatch: {} weights for {} targets".format(len(weights), len(target_paths)),
            "Ensure weights list length matches target_paths length",
            target_count=len(target_paths),
            weight_count=len(weights),
        )

    try:
        blend_node = build_blend_node(
            hou,
            driven_path=driven_path,
            target_paths=target_paths,
            weights=weights,
        )

        return skill_success(
            "Created blend constraint",
            blend_node_path=blend_node.path(),
            driven_path=driven_path,
            target_paths=target_paths,
            weights=weights if weights else None,
            target_count=len(target_paths),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create blend constraint")


@skill_entry
def main(**kwargs) -> dict:
    return create_blend_constraint(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
