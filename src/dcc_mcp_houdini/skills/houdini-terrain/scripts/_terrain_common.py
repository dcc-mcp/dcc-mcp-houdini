"""Heightfield terrain authoring helpers shared by the terrain skill tools."""

TERRAIN_LAYER_TYPES = {
    "noise": "heightfield_noise",
    "erode": "heightfield_erode",
    "terrace": "heightfield_terrace",
    "distort": "heightfield_distort",
    "scatter": "heightfield_scatter",
    "slump": "heightfield_slump",
    "flowfield": "heightfield_flowfield",
    "mask_noise": "heightfield_masknoise",
    "copy_layer": "heightfield_copylayer",
    "remap": "heightfield_remap",
}


def validate_choice(value, mapping, label):
    if value not in mapping:
        raise ValueError("Unsupported {}: {!r}".format(label, value))
    return mapping[value]
