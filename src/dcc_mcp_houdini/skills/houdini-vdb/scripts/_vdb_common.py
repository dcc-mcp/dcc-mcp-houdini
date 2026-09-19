"""VDB volume authoring helpers shared by the volume skill tools."""

from dcc_mcp_houdini._domain_graph import resolve_inputs

VDB_TYPES = {
    "from_polygons": "vdbfrompolygons",
    "from_particles": "vdbfromparticles",
    "from_volume": "vdbfromvolume",
    "combine": "vdbcombine",
    "resample": "vdbresample",
    "smooth": "vdbsmooth",
    "convert": "vdbconvert",
    "analyze": "vdbanalyze",
    "activate": "vdbactivate",
    "clip": "vdbclip",
    "advect": "vdbadvect",
    "project_nonsampled": "vdbprojectnonsampled",
}

# VDB operations that consume a second input grid.
TWO_INPUT_TYPES = {"combine", "advect"}


def validate_choice(value, mapping, label):
    if value not in mapping:
        raise ValueError("Unsupported {}: {!r}".format(label, value))
    return mapping[value]


def resolve_vdb_sources(hou, parent, paths):
    """Resolve ordered VDB inputs, rejecting anything outside ``parent``.

    Both VDB tools share this helper so a source is validated the same way
    whichever tool creates the node. Cross-network inputs are rejected rather
    than silently allowed, matching ``resolve_inputs`` elsewhere in the adapter.
    """
    return resolve_inputs(hou, parent, [path for path in paths if path is not None])


def wire_inputs(node, sources):
    """Wire each resolved source into the matching input index."""
    for index, source in enumerate(sources):
        if source is not None:
            node.setInput(index, source)
    return [index for index, source in enumerate(sources) if source is not None]
