"""Attach a POP behavior node (kill, replicate, split, ...) to a POP solver."""

from _particles_common import BEHAVIOR_TYPES, attach_pop_node, validate_choice
from dcc_mcp_core.skill import skill_entry, skill_exception

from dcc_mcp_houdini._domain_graph import hou_missing_error


def add_particle_behavior(
    network_path: str, behavior_type: str, node_name: str = None, parameters=None, connect_to: str = None
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = validate_choice(behavior_type, BEHAVIOR_TYPES, "behavior_type")
        return attach_pop_node(
            hou,
            network_path,
            node_type,
            node_name=node_name,
            parameters=parameters,
            connect_to=connect_to,
            kind="POP behavior",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to add particle behavior")


@skill_entry
def main(**kwargs):
    return add_particle_behavior(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
