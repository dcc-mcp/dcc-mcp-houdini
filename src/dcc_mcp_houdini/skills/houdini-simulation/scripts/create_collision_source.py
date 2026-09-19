"""Create a DOP collision object bound to a SOP path."""

from contextlib import ExitStack

from _simulation_common import COLLISION_TYPES, apply_parameters, find_solver, next_free_input, validate_choice
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    require_category,
    validate_identifier,
)


def create_collision_source(
    dopnet_path: str,
    source_path: str,
    collision_type: str = "static",
    node_name: str = "staticobject1",
    connect_to: str = None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = validate_choice(collision_type, COLLISION_TYPES, "collision_type")
        validate_identifier(node_name)
        dopnet = require_category(get_node(hou, dopnet_path), "Dop", children=True)
        source = get_node(hou, source_path)
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(dopnet, node_type, node_name))
            overrides = dict(parameters or {})
            overrides.setdefault("soppath", source.path())
            if collision_type == "deforming":
                overrides.setdefault("deforming", 1)
            applied, skipped = stack.enter_context(apply_parameters(created, overrides))
            target = find_solver(dopnet) if connect_to is None else get_node(hou, connect_to)
            attached_index = None
            if target is not None:
                if target.parent() is not dopnet:
                    raise ValueError("connect_to must name a node inside {}".format(dopnet.path()))
                attached_index = next_free_input(target)
                target.setInput(attached_index, created)
            return skill_success(
                "Created collision source",
                node=node_summary(created),
                node_path=created.path(),
                collision_type=collision_type,
                source_path=source.path(),
                attached_to=target.path() if target is not None else None,
                attached_input_index=attached_index,
                applied_parameters=applied,
                skipped_parameters=skipped,
                setup_state="attached" if target is not None else "unattached",
                simulation_verified=False,
                required_setup=[
                    "confirm the collision geometry resolution matches the solver",
                    "simulation cook",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create collision source")


@skill_entry
def main(**kwargs):
    return create_collision_source(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
