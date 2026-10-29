"""Copernicus-only helpers; legacy COP2 networks are rejected."""

from _cop_terrain import TERRAIN_GENERATOR_TYPES

from dcc_mcp_houdini._domain_graph import get_node, require_category, validate_node_type

FILTER_TYPES = {"comp": "blend", "composite": "blend", "color_correct": "colorcorrect", "output": "rop_image"}

# Readable aliases for the Copernicus COP terrain generators (fractal sample /
# heightfield strata). Merged into filter-type resolution so create_cop_node and
# build_composite_chain accept them exactly like any other alias.
FILTER_TYPES.update(TERRAIN_GENERATOR_TYPES)


def require_cop_network(hou, node_path):
    return require_category(get_node(hou, node_path), "Cop", children=True)


def resolve_filter_type(filter_type):
    value = validate_node_type(filter_type)
    return FILTER_TYPES.get(value, value)
