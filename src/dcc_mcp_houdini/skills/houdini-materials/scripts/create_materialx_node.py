"""Add a node to an existing MaterialX subnetwork."""

from contextlib import ExitStack

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    parameter_edit,
    validate_identifier,
    validate_node_type,
)


def create_materialx_node(material_path: str, node_type: str, node_name: str = None, parameters=None) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        resolved_type = validate_node_type(node_type)
        node_name = validate_identifier(node_name or resolved_type.split("::")[0].replace(":", "_") + "1")
        material = get_node(hou, material_path)
        if not callable(getattr(material, "children", None)):
            raise ValueError("material_path must name a network with children: {}".format(material_path))
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(material, resolved_type, node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            return skill_success(
                "Created MaterialX node",
                node=node_summary(created),
                material_path=material.path(),
                node_path=created.path(),
                node_type=created.type().name(),
                applied_parameters=applied,
                setup_state="unwired",
                required_setup=[
                    "wire the node into the surface graph",
                    "connect its output to the material output node",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create MaterialX node")


@skill_entry
def main(**kwargs):
    return create_materialx_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
