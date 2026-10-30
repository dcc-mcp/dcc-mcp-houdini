"""Create a typed Copernicus COP terrain-generator node (fractal sample / strata).

Resolves a readable alias (``fractal_sample``, ``fractal_noise``,
``fractal_noise_3d``, ``strata``, ``heightfield_strata``) to the real H22
Copernicus node type, applies bounded parameter overrides, and wires existing
input nodes. Parameter overrides go through ``parameter_edit``: a name the node
does not expose fails the call and rolls back, so this tool never silently
skips a parameter. It creates and wires nodes only; it does not cook and never
claims a rendered artifact.
"""

from contextlib import ExitStack

from _cop_terrain import generator_family, resolve_terrain_generator
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import (
    get_node,
    hou_missing_error,
    input_connections,
    owned_node,
    parameter_edit,
    require_category,
    resolve_inputs,
    validate_parameters,
)


def create_terrain_generator(
    network_path: str,
    generator_type: str,
    node_name: str = None,
    input_nodes=None,
    parameters=None,
) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        node_type = resolve_terrain_generator(generator_type)
        family = generator_family(generator_type)
        validate_parameters(parameters)
        network = require_category(get_node(hou, network_path), "Cop", children=True)
        sources = resolve_inputs(hou, network, input_nodes)
        with ExitStack() as stack:
            node = stack.enter_context(owned_node(network, node_type, node_name))
            applied = stack.enter_context(parameter_edit(node, parameters))
            for index, source in enumerate(sources):
                node.setInput(index, source)
            wired = input_connections(node)
            if [(item["input_index"], item["source_path"]) for item in wired] != list(
                enumerate(s.path() for s in sources)
            ):
                raise RuntimeError("Input wiring readback mismatch")
            return skill_success(
                "Created Copernicus terrain generator",
                network_path=network.path(),
                node_path=node.path(),
                node_type=node.type().name(),
                generator_type=generator_type,
                family=family,
                applied_parameters=applied,
                wired_inputs=wired,
                setup_state="wired" if sources else "unwired",
                required_setup=([] if sources else ["wire a source into the generator's input 0 (if required)"])
                + ["cook the chain (cook_cop_node)", "render and verify with inspect_cop_output"],
                artifact_verified=False,
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create terrain generator")


@skill_entry
def main(**kwargs):
    return create_terrain_generator(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
