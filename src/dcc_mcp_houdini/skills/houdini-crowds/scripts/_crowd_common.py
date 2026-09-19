"""Crowd authoring helpers shared by the crowd skill tools."""


def validate_choice(value, mapping, label):
    if value not in mapping:
        raise ValueError("Unsupported {}: {!r}".format(label, value))
    return mapping[value]
