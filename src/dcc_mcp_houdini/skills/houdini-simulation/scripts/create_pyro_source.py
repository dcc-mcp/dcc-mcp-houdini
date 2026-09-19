"""Create a pyro source SOP that turns geometry into volume source attributes."""

from contextlib import ExitStack

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    node_summary,
    owned_node,
    parameter_edit,
    require_category,
    validate_identifier,
)

PYRO_SOURCE_TYPES = {"sop": "pyrosource", "volume": "volumesource"}


def create_pyro_source(
    parent_path: str,
    source_path: str = None,
    source_type: str = "sop",
    node_name: str = None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if source_type not in PYRO_SOURCE_TYPES:
            raise ValueError("Unsupported source_type: {!r}".format(source_type))
        node_type = PYRO_SOURCE_TYPES[source_type]
        node_name = validate_identifier(node_name or node_type + "1")
        parent = require_category(get_node(hou, parent_path), "Sop", children=True)
        source = get_node(hou, source_path) if source_path else None
        with ExitStack() as stack:
            created = stack.enter_context(owned_node(parent, node_type, node_name))
            applied = stack.enter_context(parameter_edit(created, parameters))
            wired = False
            if source is not None:
                created.setInput(0, source)
                wired = True
            return skill_success(
                "Created pyro source",
                node=node_summary(created),
                node_path=created.path(),
                node_type=created.type().name(),
                source_type=source_type,
                source_path=source.path() if source is not None else None,
                wired=wired,
                applied_parameters=applied,
                setup_state="wired" if wired else "unwired",
                simulation_verified=False,
                required_setup=[
                    "connect the source to the pyro solver's source input",
                    "bind the source volume names to the solver fields",
                    "simulation cook",
                ],
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create pyro source")


@skill_entry
def main(**kwargs):
    return create_pyro_source(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
