"""VDB volume authoring helpers shared by the volume skill tools."""

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


def wire_inputs(node, sources):
    """Wire each resolved source into the matching input index."""
    for index, source in enumerate(sources):
        if source is not None:
            node.setInput(index, source)
    return [index for index, source in enumerate(sources) if source is not None]
