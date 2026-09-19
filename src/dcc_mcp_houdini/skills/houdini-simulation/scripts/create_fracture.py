"""Create a fracture SOP for RBD pre-fracture with optional source wiring."""

from contextlib import ExitStack

from _simulation_common import FRACTURE_TYPES, apply_parameters, validate_choice
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    require_category,
    validate_identifier,
)


def create_fracture(
    parent_path: str,
    fracture_type: str,
    source_path: str = None,
    node_name: str = "fracture1",
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = validate_choice(fracture_type, FRACTURE_TYPES, "fracture_type")
        validate_identifier(node_name)
        parent = require_category(get_node(hou, parent_path), "Sop", children=True)
        source = get_node(hou, source_path) if source_path else None
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, node_type, node_name))
            applied, skipped = stack.enter_context(apply_parameters(created, parameters))
            wired = False
            if source is not None:
                created.setInput(0, source)
                wired = True
            return skill_success(
                "Created fracture node",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                fracture_type=fracture_type,
                source_path=source.path() if source is not None else None,
                wired=wired,
                applied_parameters=applied,
                skipped_parameters=skipped,
                setup_state="skeleton" if not wired else "wired",
                simulation_verified=False,
                required_setup=[
                    "scatter fracture source points",
                    "pack or assemble inside pieces",
                    "connect the result to an RBD solver",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create fracture node")


@skill_entry
def main(**kwargs):
    return create_fracture(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
