"""UV authoring helpers shared by the UV skill tools."""

UNWRAP_TYPES = {
    "auto": "uvunwrap",
    "atlas": "uvlayout",
    "flatten": "uvflatten",
    "pelt": "uvpelt",
    "quick": "uvquickshade",
}

TRANSFORM_TYPES = {
    "transform": "uvtransform",
    "edit": "uvedit",
    "fuse": "uvfuse",
    "fit": "uvfit",
    "layout": "uvlayout",
}


def validate_choice(value, mapping, label):
    if value not in mapping:
        raise ValueError("Unsupported {}: {!r}".format(label, value))
    return mapping[value]
