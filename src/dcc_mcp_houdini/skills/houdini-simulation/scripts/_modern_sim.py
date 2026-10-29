"""Host-independent catalog for four modern Houdini node families.

This module makes four recent Houdini feature families discoverable through
stable, readable aliases instead of raw (and version-sensitive) node type
names:

* ``rbd_material_fracture`` -- the SOP ``rbdmaterialfracture`` node and its
  material-specific variants (concrete / glass / wood).
* ``cops_pyro`` -- the GPU 2D pyro nodes in a Copernicus ``copnet``
  (``pyro_configure`` / ``pyro_sourcefromvolume`` / ``pyro_block_begin`` ...).
* ``sparse_gpu_pyro`` -- the DOP sparse pyro solver family
  (``pyrosolver_sparse`` / ``smokeobject_sparse`` / ``gasopencl``).
* ``rasterize_volume`` -- volume-to-raster nodes
  (``rasterizevolume`` / ``rasterizesetup`` in COP, ``volumerasterize`` in SOP).

The node type names and the recommended parameter names were confirmed against
a live Houdini 22.0.368 host (Sop/Cop/Dop ``nodeTypeCategory().nodeTypes()``).
This module is pure stdlib: it never imports ``hou``, touches a scene, or
cooks. Keeping it host-independent makes the alias/plan contract unit-testable
without a Houdini install and keeps every shipped source Python 3.7-parseable.

Authoring (creating/wiring nodes) is the job of
:mod:`create_modern_sim_node`; this module only resolves aliases and returns
deterministic, JSON-safe authoring plans. It never claims a cooked or rendered
artifact.
"""

from __future__ import annotations

# The four feature families addressed by this enhancement.
FAMILY_RBD_MATERIAL_FRACTURE = "rbd_material_fracture"
FAMILY_COPS_PYRO = "cops_pyro"
FAMILY_SPARSE_GPU_PYRO = "sparse_gpu_pyro"
FAMILY_RASTERIZE_VOLUME = "rasterize_volume"

FAMILIES = (
    FAMILY_RBD_MATERIAL_FRACTURE,
    FAMILY_COPS_PYRO,
    FAMILY_SPARSE_GPU_PYRO,
    FAMILY_RASTERIZE_VOLUME,
)

# Readable alias -> real Houdini node type + the child category of the parent
# network a node of that type is created in. ``category`` is deliberately
# per-alias (not per-family): the ``rasterize_volume`` family spans both COP
# (rasterizevolume) and SOP (volumerasterize) contexts.
MODERN_SIM_NODES = {
    # --- RBD material fracture (SOP) ---
    "rbd_material_fracture": {
        "node_type": "rbdmaterialfracture",
        "category": "Sop",
        "family": FAMILY_RBD_MATERIAL_FRACTURE,
    },
    "rbd_concrete_fracture": {
        "node_type": "rbdconcretefracture",
        "category": "Sop",
        "family": FAMILY_RBD_MATERIAL_FRACTURE,
    },
    "rbd_glass_fracture": {"node_type": "rbdglassfracture", "category": "Sop", "family": FAMILY_RBD_MATERIAL_FRACTURE},
    "rbd_wood_fracture": {"node_type": "rbdwoodfracture", "category": "Sop", "family": FAMILY_RBD_MATERIAL_FRACTURE},
    # --- COps pyro (Copernicus / COP) ---
    "pyro_configure": {"node_type": "pyro_configure", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_source_volume": {"node_type": "pyro_sourcefromvolume", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_source_layer": {"node_type": "pyro_sourcefromlayer", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_block_begin": {"node_type": "pyro_block_begin", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_block_end": {"node_type": "pyro_block_end", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_advect": {"node_type": "pyro_advect", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_buoyancy": {"node_type": "pyro_buoyancy", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_turbulence": {"node_type": "pyro_turbulence", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_disturbance": {"node_type": "pyro_disturbance", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_vortex_confinement": {"node_type": "pyro_vortexconfinement", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_dissipate": {"node_type": "pyro_dissipate", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_activate": {"node_type": "pyro_activate", "category": "Cop", "family": FAMILY_COPS_PYRO},
    "pyro_advection_map": {"node_type": "pyro_buildadvectionmap", "category": "Cop", "family": FAMILY_COPS_PYRO},
    # --- Sparse GPU pyro (DOP) ---
    "pyro_sparse_solver": {"node_type": "pyrosolver_sparse", "category": "Dop", "family": FAMILY_SPARSE_GPU_PYRO},
    "smoke_sparse_object": {"node_type": "smokeobject_sparse", "category": "Dop", "family": FAMILY_SPARSE_GPU_PYRO},
    "smoke_sparse_solver": {"node_type": "smokesolver_sparse", "category": "Dop", "family": FAMILY_SPARSE_GPU_PYRO},
    "gas_opencl": {"node_type": "gasopencl", "category": "Dop", "family": FAMILY_SPARSE_GPU_PYRO},
    # --- rasterize Volume (COP + SOP) ---
    "rasterize_volume": {"node_type": "rasterizevolume", "category": "Cop", "family": FAMILY_RASTERIZE_VOLUME},
    "rasterize_setup": {"node_type": "rasterizesetup", "category": "Cop", "family": FAMILY_RASTERIZE_VOLUME},
    "volume_rasterize": {"node_type": "volumerasterize", "category": "Sop", "family": FAMILY_RASTERIZE_VOLUME},
    "volume_rasterize_attributes": {
        "node_type": "volumerasterizeattributes",
        "category": "Sop",
        "family": FAMILY_RASTERIZE_VOLUME,
    },
}

# Reverse map so a raw (already resolved) Houdini node type is also accepted.
_NODE_TYPE_META = {}
for _meta in MODERN_SIM_NODES.values():
    _NODE_TYPE_META.setdefault(_meta["node_type"], _meta)

# Aliases grouped by family, in stable declaration order.
ALIASES_BY_FAMILY = {}
for _alias, _meta in MODERN_SIM_NODES.items():
    ALIASES_BY_FAMILY.setdefault(_meta["family"], []).append(_alias)

# Documentation-only guidance, NOT auto-applied defaults. All names were read
# from live Houdini 22.0.368 parameter templates; parameter availability varies
# between builds, so the typed tool applies caller-supplied overrides through
# ``parameter_edit`` (which fails and rolls back on a name the node lacks).
RECOMMENDED_PARAMETERS = {
    FAMILY_RBD_MATERIAL_FRACTURE: (
        {"name": "materialtype", "purpose": "material preset (concrete / glass / wood)", "typical": "menu token"},
        {"name": "fracturenamespace", "purpose": "namespace prefix for generated attributes", "typical": "string"},
        {"name": "pieceattrib", "purpose": "attribute naming the fractured pieces", "typical": "string"},
        {"name": "randomseed", "purpose": "seed for repeatable fracture variation", "typical": "integer"},
        {"name": "enablecompiling", "purpose": "compile the fracture for faster cooks", "typical": "0/1"},
    ),
    FAMILY_COPS_PYRO: (
        {"name": "divmethod", "purpose": "voxel/2D division method on pyro_configure", "typical": "menu token"},
        {"name": "voxelsize", "purpose": "base voxel size of the simulation grid", "typical": "float > 0"},
        {"name": "resolution", "purpose": "grid resolution override", "typical": "integer tuple"},
        {"name": "cflcond", "purpose": "CFL safety factor on the pyro block", "typical": "0-1"},
        {"name": "maxstep", "purpose": "maximum substeps per frame", "typical": "integer >= 1"},
        {"name": "sourcemode", "purpose": "how a source volume is injected", "typical": "menu token"},
        {"name": "scale", "purpose": "source emission scale", "typical": "float"},
    ),
    FAMILY_SPARSE_GPU_PYRO: (
        {"name": "sparsesolve", "purpose": "enable sparse (GPU-friendly) solving", "typical": "0/1"},
        {"name": "twod", "purpose": "solve in 2D mode", "typical": "0/1"},
        {"name": "divsize", "purpose": "base division size of the sparse grid", "typical": "float > 0"},
        {"name": "calcspeed", "purpose": "simulation speed / time step control", "typical": "float"},
        {"name": "tempdiffusion", "purpose": "temperature diffusion rate", "typical": "float"},
        {"name": "tempcooling", "purpose": "temperature cooling rate", "typical": "float"},
        {"name": "buoyancylift", "purpose": "buoyancy lift strength", "typical": "float"},
        {"name": "kernelname", "purpose": "OpenCL kernel name on gasopencl", "typical": "string"},
    ),
    FAMILY_RASTERIZE_VOLUME: (
        {"name": "densityscale", "purpose": "scales volume density during rasterization", "typical": "float"},
        {"name": "rangemin", "purpose": "lower density remap bound", "typical": "float"},
        {"name": "rangemax", "purpose": "upper density remap bound", "typical": "float"},
        {"name": "stepsize", "purpose": "ray-march step size", "typical": "float > 0"},
        {"name": "maxstepcount", "purpose": "maximum ray-march steps", "typical": "integer >= 1"},
        {"name": "transmitcutoff", "purpose": "early-out transmittance cutoff", "typical": "0-1"},
        {"name": "samples", "purpose": "SOP volumerasterize sample count", "typical": "integer >= 1"},
    ),
}

# Deterministic authoring chains per family. Each step names a role and a
# catalog alias; ``build_modern_sim_plan`` resolves the alias to the real node
# type and category. These are guidance for agents, not an executable recipe:
# no node is created here and no cook is claimed.
FAMILY_CHAINS = {
    FAMILY_RBD_MATERIAL_FRACTURE: (
        {"role": "source", "alias": None, "parameters_hint": ["materialtype"]},
        {
            "role": "fracture",
            "alias": "rbd_material_fracture",
            "parameters_hint": ["materialtype", "fracturenamespace"],
        },
        {"role": "output", "alias": None, "parameters_hint": []},
    ),
    FAMILY_COPS_PYRO: (
        {"role": "configure", "alias": "pyro_configure", "parameters_hint": ["divmethod", "voxelsize"]},
        {"role": "source", "alias": "pyro_source_volume", "parameters_hint": ["sourcemode", "scale"]},
        {"role": "block_begin", "alias": "pyro_block_begin", "parameters_hint": ["cflcond", "maxstep"]},
        {"role": "advect", "alias": "pyro_advect", "parameters_hint": []},
        {"role": "buoyancy", "alias": "pyro_buoyancy", "parameters_hint": []},
        {"role": "turbulence", "alias": "pyro_turbulence", "parameters_hint": []},
        {"role": "dissipate", "alias": "pyro_dissipate", "parameters_hint": []},
        {"role": "block_end", "alias": "pyro_block_end", "parameters_hint": []},
    ),
    FAMILY_SPARSE_GPU_PYRO: (
        {"role": "object", "alias": "smoke_sparse_object", "parameters_hint": ["sparsesolve", "twod", "divsize"]},
        {
            "role": "solver",
            "alias": "pyro_sparse_solver",
            "parameters_hint": ["calcspeed", "tempdiffusion", "tempcooling"],
        },
        {"role": "gpu_kernel", "alias": "gas_opencl", "parameters_hint": ["kernelname"]},
    ),
    FAMILY_RASTERIZE_VOLUME: (
        {"role": "volume", "alias": None, "parameters_hint": []},
        {"role": "setup", "alias": "rasterize_setup", "parameters_hint": []},
        {
            "role": "rasterize",
            "alias": "rasterize_volume",
            "parameters_hint": ["densityscale", "stepsize", "maxstepcount"],
        },
        {"role": "output", "alias": None, "parameters_hint": []},
    ),
}

_REQUIRED_SETUP = {
    FAMILY_RBD_MATERIAL_FRACTURE: [
        "supply the geometry to fracture into input 0",
        "select/confirm the materialtype on the target Houdini build",
        "connect the fractured pieces to an RBD solver or output",
    ],
    FAMILY_COPS_PYRO: [
        "create a Copernicus network (copnet) to host the nodes",
        "verify COP node type availability on the target Houdini build",
        "wire sources into the pyro block and connect an output",
        "cook explicitly and verify an artifact with a downstream render skill",
    ],
    FAMILY_SPARSE_GPU_PYRO: [
        "create a DOP network to host the solver chain",
        "confirm a GPU/OpenCL device is available for sparse solving",
        "supply source volumes and an output",
    ],
    FAMILY_RASTERIZE_VOLUME: [
        "supply a volume/VDB as input",
        "choose the COP (rasterizevolume) or SOP (volumerasterize) path",
        "verify parameter names on the target Houdini build before applying",
    ],
}


def modern_node_meta(value):
    """Return ``{node_type, category, family, alias}`` for an alias or raw node type.

    Both friendly aliases and already-resolved raw Houdini node type names are
    accepted. Unknown values raise ``ValueError`` with the supported set so the
    vocabulary stays discoverable.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("node_type must be a non-empty string")
    meta = MODERN_SIM_NODES.get(value)
    if meta is None:
        meta = _NODE_TYPE_META.get(value)
    if meta is None:
        raise ValueError(
            "Unsupported modern simulation node: {!r}; supported aliases: {}".format(value, sorted(MODERN_SIM_NODES))
        )
    result = dict(meta)
    result["alias"] = value if value in MODERN_SIM_NODES else _primary_alias(meta)
    return result


def _primary_alias(meta):
    for alias, candidate in MODERN_SIM_NODES.items():
        if candidate is meta or candidate.get("node_type") == meta.get("node_type"):
            return alias
    return meta.get("node_type")


def resolve_modern_node(value):
    """Return the real Houdini node type for an alias (or a raw node type)."""
    return modern_node_meta(value)["node_type"]


def modern_node_category(value):
    """Return the parent child-category (Sop/Cop/Dop) required by ``value``."""
    return modern_node_meta(value)["category"]


def modern_node_family(value):
    """Return the family key for an alias (or a raw node type)."""
    return modern_node_meta(value)["family"]


def aliases_for_family(family):
    """Return the tuple of readable aliases belonging to ``family``."""
    if family not in ALIASES_BY_FAMILY:
        raise ValueError("Unsupported modern simulation family: {!r}; supported: {}".format(family, list(FAMILIES)))
    return tuple(ALIASES_BY_FAMILY[family])


def build_modern_sim_plan(family):
    """Return a deterministic, JSON-safe authoring plan for ``family``.

    The plan lists the family's node chain (resolved node types + categories),
    recommended parameter names, and required setup. It never accesses a host,
    never cooks, and always reports ``artifact_verified=False`` /
    ``simulation_verified=False``.
    """
    if family not in FAMILIES:
        raise ValueError("Unsupported modern simulation family: {!r}; supported: {}".format(family, list(FAMILIES)))
    steps = []
    for index, template in enumerate(FAMILY_CHAINS[family]):
        alias = template["alias"]
        if alias is None:
            node_type = None
            category = None
        else:
            meta = modern_node_meta(alias)
            node_type = meta["node_type"]
            category = meta["category"]
        steps.append(
            {
                "index": index,
                "role": template["role"],
                "alias": alias,
                "node_type": node_type,
                "category": category,
                "parameters_hint": list(template["parameters_hint"]),
            }
        )
    return {
        "family": family,
        "aliases": list(aliases_for_family(family)),
        "steps": steps,
        "step_count": len(steps),
        "recommended_parameters": [dict(item) for item in RECOMMENDED_PARAMETERS[family]],
        "required_setup": list(_REQUIRED_SETUP[family]),
        "validation_scope": "plan_only_no_host_access",
        "artifact_verified": False,
        "simulation_verified": False,
    }
