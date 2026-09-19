"""Attach a DOP gas micro-solver to a fluid solver input."""

from contextlib import ExitStack

from _simulation_common import find_solver
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    next_free_input,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
)

GAS_FIELD_TYPES = {
    "turbulence": "gasturbulence",
    "disturbance": "gasdisturbance",
    "vortex_confinement": "gasvortexconfinement",
    "resize": "gasresizefluiddynamic",
    "dissipation": "gasdissipation",
    "target_field": "gastargetfield",
}


def add_gas_field(
    dopnet_path: str,
    field_type: str,
    node_name: str = None,
    parameters=None,
    connect_to: str = None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if field_type not in GAS_FIELD_TYPES:
            raise ValueError("Unsupported field_type: {!r}".format(field_type))
        node_type = GAS_FIELD_TYPES[field_type]
        node_name = validate_identifier(node_name or node_type + "1")
        dopnet = require_category(get_node(hou, dopnet_path), "Dop", children=True)
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(dopnet, node_type, node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            target = find_solver(dopnet) if connect_to is None else get_node(hou, connect_to)
            attached_index = None
            if target is not None:
                if target.parent() is not dopnet:
                    raise ValueError("connect_to must name a node inside {}".format(dopnet.path()))
                attached_index = next_free_input(target)
                target.setInput(attached_index, created)
            return skill_success(
                "Added gas micro-solver",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                field_type=field_type,
                dopnet_path=dopnet.path(),
                attached_to=target.path() if target is not None else None,
                attached_input_index=attached_index,
                applied_parameters=applied,
                setup_state="attached" if target is not None else "unattached",
                simulation_verified=False,
                required_setup=[] if target is not None else ["connect the micro-solver into the solver chain"],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to add gas field")


@skill_entry
def main(**kwargs):
    return add_gas_field(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
