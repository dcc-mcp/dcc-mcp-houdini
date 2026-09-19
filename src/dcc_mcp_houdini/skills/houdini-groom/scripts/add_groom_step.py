"""Add a single grooming SOP step to an existing fur or hair chain."""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
)

GROOM_STEP_TYPES = {
    "generate": "hairgen",
    "clump": "hairclump",
    "guide_deform": "guidedeform",
    "frizz": "frizz",
    "brush": "brush",
    "guide_groom": "guidegroom",
    "hair_card": "haircard",
    "copy": "haircopy",
}


def add_groom_step(
    geo_path: str,
    step_type: str,
    source_path: Optional[str] = None,
    node_name: Optional[str] = None,
    parameters: Any = None,
) -> dict:
    try:
        import hou
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        if step_type not in GROOM_STEP_TYPES:
            raise ValueError(
                "Unsupported step_type: {!r}; expected one of {}".format(step_type, ", ".join(sorted(GROOM_STEP_TYPES)))
            )
        node_type = GROOM_STEP_TYPES[step_type]
        node_name = validate_identifier(node_name or node_type + "1")
        parent = require_category(get_node(hou, geo_path), "Sop", children=True)
        source = get_node(hou, source_path) if source_path else None
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, node_type, node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            wired = False
            if source is not None:
                created.setInput(0, source)
                wired = True
            return skill_success(
                "Added groom step",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                step_type=step_type,
                source_path=source.path() if source is not None else None,
                wired=wired,
                applied_parameters=applied,
                setup_state="wired" if wired else "unwired",
                required_setup=[] if wired else ["wire the step into the groom chain"],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to add groom step")


@skill_entry
def main(**kwargs):
    return add_groom_step(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
