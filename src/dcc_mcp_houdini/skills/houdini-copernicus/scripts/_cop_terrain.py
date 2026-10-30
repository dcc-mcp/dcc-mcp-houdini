"""Houdini-independent helpers for Copernicus COP terrain generators.

Two Copernicus node families back COPS heightfield terrain authoring:

* ``fractal sample`` -- procedural fractal noise used as the height source
  (``fractalsample`` / ``fractalnoise`` / ``fractalnoise3d``).
* ``heightfield strata`` -- stratified/sedimentary rock layers applied to a
  height layer (``heightfield_strata``).

The node type names were confirmed against a live Houdini 22.0.368 Copernicus
host by the COPS heightfield ground tests (see the SKILL.md "Copernicus
terrain generators" section). This module is pure stdlib: it has no ``hou``
import and no filesystem side effects, so the alias/plan contract is
unit-testable without a Houdini install and every shipped source stays Python
3.7-parseable. It never claims a cooked artifact; building/wiring the node is
the job of :mod:`create_terrain_generator`.
"""

# Readable alias -> real H22 Copernicus COP node type. Keys are accepted by the
# typed tool and by create_cop_node/build_composite_chain via resolve_filter_type.
FRACTAL_SAMPLE_GENERATORS = {
    "fractal_sample": "fractalsample",
    "fractal_noise": "fractalnoise",
    "fractal_noise_3d": "fractalnoise3d",
}

STRATA_GENERATORS = {
    "strata": "heightfield_strata",
    "heightfield_strata": "heightfield_strata",
}

TERRAIN_GENERATOR_TYPES = {}
TERRAIN_GENERATOR_TYPES.update(FRACTAL_SAMPLE_GENERATORS)
TERRAIN_GENERATOR_TYPES.update(STRATA_GENERATORS)

FRACTAL_SAMPLE_ALIASES = frozenset(FRACTAL_SAMPLE_GENERATORS)
STRATA_ALIASES = frozenset(STRATA_GENERATORS)

_FAMILIES = {}
for _alias in FRACTAL_SAMPLE_GENERATORS:
    _FAMILIES[_alias] = "fractal_sample"
for _alias in STRATA_GENERATORS:
    _FAMILIES[_alias] = "strata"

# Documentation-only guidance, NOT auto-applied defaults. Copernicus parameter
# names vary between Houdini builds; the typed tool applies caller-supplied
# parameters through parameter_edit, which fails and rolls back on a name the
# node does not expose. See SKILL.md "Parameter policy".
RECOMMENDED_PARAMETERS = {
    "fractal_sample": (
        {"name": "freq", "purpose": "base noise frequency (smaller = broader features)", "typical": "1-8"},
        {"name": "oct", "purpose": "fractal octaves / detail layers", "typical": "1-16"},
        {"name": "rough", "purpose": "amplitude falloff between octaves", "typical": "0-1"},
        {"name": "lac", "purpose": "frequency multiplier between octaves", "typical": "2.0"},
        {"name": "amp", "purpose": "final height amplitude", "typical": "0-1"},
        {"name": "seed", "purpose": "noise seed for reproducibility", "typical": "integer"},
    ),
    "strata": (
        {"name": "layers", "purpose": "number of sedimentary strata", "typical": "integer >= 1"},
        {"name": "seed", "purpose": "layer variation seed", "typical": "integer"},
        {"name": "freq", "purpose": "strata wobble frequency", "typical": "1-8"},
    ),
}

# The layer -> heightfield conversion chain proven by the COPS heightfield
# ground tests: a fractal-noise mono layer becomes a heightfield Volume, strata
# is applied, and the result is turned back into a mono layer for a ROP output.
# The source step's node_type/alias are placeholders: build_terrain_plan fills
# them from the selected generator so they can never disagree.
TERRAIN_CHAIN_TEMPLATE = (
    {"role": "source", "alias": None, "node_type": None},
    {"role": "to_mono", "alias": None, "node_type": "mono"},
    {"role": "to_heightfield", "alias": None, "node_type": "monotoheightfield"},
    {"role": "strata", "alias": "strata", "node_type": "heightfield_strata"},
    {"role": "from_heightfield", "alias": None, "node_type": "heightfieldtomono"},
    {"role": "output", "alias": None, "node_type": "rop_image"},
)

# node_type -> canonical readable alias for the fractal-sample source family.
# This family maps aliases to node types 1:1, so the reverse is unambiguous;
# it keeps the source step's alias stable even when a caller passes a raw
# Houdini node type instead of an alias.
_SOURCE_ALIAS_BY_NODE_TYPE = {node_type: alias for alias, node_type in FRACTAL_SAMPLE_GENERATORS.items()}


def resolve_terrain_generator(value):
    """Return the real COP node type for a readable alias (or a raw node type).

    Both the friendly aliases and the already-resolved node type names are
    accepted so callers can pass either. Unknown values raise ValueError with
    the supported set, keeping the vocabulary discoverable.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("generator_type must be a non-empty string")
    if value in TERRAIN_GENERATOR_TYPES:
        return TERRAIN_GENERATOR_TYPES[value]
    known_types = set(TERRAIN_GENERATOR_TYPES.values())
    if value in known_types:
        return value
    raise ValueError(
        "Unsupported terrain generator: {!r}; supported aliases: {}".format(value, sorted(TERRAIN_GENERATOR_TYPES))
    )


def generator_family(value):
    """Return ``'fractal_sample'`` or ``'strata'`` for an alias/raw node type."""
    if not isinstance(value, str) or not value:
        raise ValueError("generator_type must be a non-empty string")
    if value in _FAMILIES:
        return _FAMILIES[value]
    for alias, node_type in TERRAIN_GENERATOR_TYPES.items():
        if node_type == value and alias in _FAMILIES:
            return _FAMILIES[alias]
    raise ValueError(
        "Unknown terrain generator: {!r}; supported aliases: {}".format(value, sorted(TERRAIN_GENERATOR_TYPES))
    )


def build_terrain_plan(generator, with_strata=True, with_output=True):
    """Return a deterministic, JSON-safe authoring plan (no host access).

    The plan describes the chain of Copernicus node types to build and wire;
    it never cooks or claims a rendered artifact. ``generator`` selects the
    fractal-sample source node used at the head of the chain, so it must be a
    fractal-sample generator (strata is a mid-chain layer, not a source).
    """
    node_type = resolve_terrain_generator(generator)
    family = generator_family(generator)
    if family != "fractal_sample":
        raise ValueError(
            "Plan head must be a fractal-sample generator, got {!r} (family {!r}); "
            "strata is applied as a mid-chain layer".format(generator, family)
        )
    # The head alias must name the same generator as the head node_type. Derive
    # it from the resolved node type so an alias, a raw node type, and the plan
    # step all stay consistent (strata has two aliases, but the fractal-sample
    # family is 1:1). Other steps keep their template alias.
    source_alias = _SOURCE_ALIAS_BY_NODE_TYPE[node_type]
    steps = []
    for template_step in TERRAIN_CHAIN_TEMPLATE:
        role = template_step["role"]
        if role == "strata" and not with_strata:
            continue
        if role == "output" and not with_output:
            continue
        is_source = role == "source"
        steps.append(
            {
                "role": role,
                "node_type": node_type if is_source else template_step["node_type"],
                "alias": source_alias if is_source else template_step["alias"],
                "parameters_hint": list(RECOMMENDED_PARAMETERS[family]) if is_source else [],
            }
        )
    return {
        "generator": generator,
        "node_type": node_type,
        "family": family,
        "steps": steps,
        "step_count": len(steps),
        "required_setup": [
            "create a Copernicus network (create_cop_network)",
            "verify parameter names on the target Houdini build before applying (see RECOMMENDED_PARAMETERS)",
            "build and wire the chain (create_terrain_generator / build_composite_chain)",
            "cook the chain (cook_cop_node)",
            "render with houdini_render__render_rop and verify with inspect_cop_output",
        ],
        "recommended_parameters": {
            "fractal_sample": [dict(item) for item in RECOMMENDED_PARAMETERS["fractal_sample"]],
            "strata": [dict(item) for item in RECOMMENDED_PARAMETERS["strata"]],
        },
        "validation_scope": "plan_only_no_host_access",
        "artifact_verified": False,
    }
