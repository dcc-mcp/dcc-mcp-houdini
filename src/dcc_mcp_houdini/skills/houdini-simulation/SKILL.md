---
name: houdini-simulation
description: >-
  Typed DOP simulation tools for Pyro, FLIP, RBD, and Vellum. Create a
  solver network, apply bounded parameters, inspect solver state and cached
  DOP field dimensions, validate a
  setup before committing to a long cook, and build the fracture, constraint
  network, collision, pyro source and gas micro-solver building blocks that
  those solver families need.
license: MIT
compatibility: "Python 3.7+, dcc-mcp-houdini 0.38+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, dop, simulation, pyro, flip, rbd, vellum, fracture, constraint, collision, gas, solver, validation]
    search-hint: "pyro flip fluid rbd rigid vellum cloth grains dop solver simulation fracture glue collision gas turbulence cache validate field metadata resolution voxel size pressure velocity"
    tools: tools.yaml
---

# houdini-simulation

Typed DOP skeleton authoring and structural validation for four simulation
families, plus the fracture, constraint and collision building blocks those
families need. This creates a container and solver, not a runnable simulation template.
Callers must supply object/source geometry, wiring and an output before cooking. The skill deliberately separates setup from cooking: an agent can
create and inspect a solver network, read back the applied parameters, and
only then hand the node to a render or automation workflow for a long cook.

## Supported solver families

- `pyro` → `pyrosolver`
- `flip` → `flipsolver`
- `rbd` → `rbdsolver`
- `vellum` → `vellumsolver`

The node type is still resolved by Houdini at runtime. A missing solver or an
unsupported Houdini build returns a structured skill error instead of silently
creating a different simulation.

## Rigid-body building blocks

| Tool | Creates | Notes |
|------|---------|-------|
| `create_fracture` | `voronoifracture`, `booleanfracture`, `rbdmaterialfracture` | SOP level; wires `source_path` into input 0 when given |
| `create_constraint_network` | `constraintnetwork` (+ `glueconrel`, `bulletsoftconrel`, `conetwistconrel`) | DOP level; optional relationship is created in the same DOP network and wired to input 1; pass constraint geometry through `parameters.soppath` |
| `create_collision_source` | `staticobject` | DOP level; sets `soppath` and attaches to the first solver input |

These three tools report parameters they cannot apply through
`skipped_parameters`. Fracture and collision tools seed best-effort defaults
that Houdini builds may not expose; constraint geometry is only assigned when
the caller explicitly supplies `parameters.soppath`.

Every other tool in this package has no `skipped_parameters` field: it applies
caller overrides through `parameter_edit`, so an override the node does not
expose **fails the call and rolls back** rather than being skipped silently.

## Tracer-bullet flow

1. `create_simulation_network(parent_path="/obj", simulation_type="pyro")`
2. `configure_simulation_solver(solver_path="/obj/dopnet1/pyrosolver1", parameters={...})`
3. `inspect_simulation_network(network_path="/obj/dopnet1")`
4. `validate_simulation_setup(network_path="/obj/dopnet1", simulation_type="pyro")`
5. Supply the required object/source and output connections, then use the
   existing render or automation skills for an explicitly requested cook.

## Cached field inspection

`inspect_simulation_fields(network_path="/obj/dopnet1", object_name="water",
field_names=["surface", "vel", "pressure"])` reads the current simulation's
field types and per-component names, primitive types, resolutions and voxel
sizes. Staggered vector components keep their distinct dimensions. No field
values are sampled and no pressure units are inferred.

The network must have a positive `cookCount()` and `needsToCook() is False`;
missing or failing guards refuse inspection before accessing the simulation.
This checks the network's reported state, not whether every child edit has
reached the simulation. A child parameter edit can leave the network reporting
`False` while cached metadata still describes the previous solve.
There is no frame selection or cook option. The tool compares frame, cook count
and simulation time before and after reading, and fails if they change.
HOM does not document a cached-only guarantee for
[`fieldGeometry`](https://www.sidefx.com/docs/houdini/hom/hou/DopData.html#fieldGeometry); this guard
and readback are not a substitute for native validation on the target build.

Names are exact, without patterns. Omit `field_names` to inspect only direct
subdata entries; explicit relative paths can select nested data without a
recursive search. At most `max_fields` entries (default 16, maximum 32) are
read, with `total_entries` and `truncated` reporting the bound. Each entry has
`status` `ok`, `missing`, `not_field`, or `read_error`; inspect these statuses
even when the overall inspection succeeds. More than 16 components is a
`read_error`. This is metadata inspection, not simulation verification.

## Rigid-body flow

1. `create_fracture(parent_path="/obj/geo1", fracture_type="voronoi", source_path="/obj/geo1/box1")`
2. `create_simulation_network(parent_path="/obj", simulation_type="rbd")`
3. `create_constraint_network(dopnet_path="/obj/dopnet1", constraint_type="glue", relationship_parent="/obj/dopnet1", parameters={"soppath": "/obj/geo1/constraints"})`
4. `create_collision_source(dopnet_path="/obj/dopnet1", source_path="/obj/geo1/ground1")`
5. `validate_simulation_setup(network_path="/obj/dopnet1", simulation_type="rbd")`

Constraint geometry and relationship data are separate: `soppath` reads SOP
geometry, while the relationship is a DOP whose Data Name must match the
geometry's `constraint_name` attribute. Glue, Bullet soft and cone-twist
relationships require a Bullet solver. `relationship_parent` now requires the
same DOP network; the previous SOP-parent contract could not create these node
types. The previously advertised `wire` choice had no native `wireconrel`
node and is rejected rather than substituted with a different constraint.

## Pyro and volumetric building blocks

| Tool | Creates | Level |
|------|---------|-------|
| `create_pyro_source` | `pyrosource`, `volumesource` | SOP |
| `add_pyro_post_process` | `pyropostprocess` | SOP |
| `add_gas_field` | `gasturbulence`, `gasdisturbance`, `gasvortexconfinement`, `gasresizefluiddynamic`, `gasdissipation`, `gastargetfield` | DOP |

### Pyro flow

1. `create_pyro_source(parent_path="/obj/geo1", source_path="/obj/geo1/sphere1")`
2. `create_simulation_network(parent_path="/obj", simulation_type="pyro")`
3. `add_gas_field(dopnet_path="/obj/dopnet1", field_type="turbulence")`
4. `add_pyro_post_process(parent_path="/obj/geo1", source_path="/obj/geo1/dopimport1")`

`add_gas_field` attaches the micro-solver to the first free input of the first
solver it finds in the network; pass `connect_to` to choose a different target.
When no solver exists the node is created unattached and reported with
`setup_state="unattached"`.

Volumetric (OpenVDB) authoring lives in the sibling `houdini-vdb` skill.
Particle (POP) authoring lives in the sibling `houdini-particles` skill.

Validation includes child errors and disconnected solvers. It reports its
structural scope and always leaves `simulation_verified=false`; a cached error
check cannot establish a successful simulation.

Parameters are checked before writing and read back after writing. Missing
parameters fail explicitly. Failed edits restore parameter values, expressions
and animation; failed creation removes only nodes owned by that request.

## Modern Houdini node families (H21+)

Four recent Houdini feature families are exposed through stable aliases so an
agent does not have to guess version-sensitive node type names. The node types
and recommended parameter names below were confirmed against a live Houdini
22.0.368 host; availability still varies between builds, so the typed creator
applies caller-supplied parameters through `parameter_edit` (an unknown name
fails the call and rolls back). Recommended parameters are guidance, not
auto-applied defaults — verify names on the target build before applying.

| Family | Aliases (examples) | Node category | Real node types (examples) |
|--------|--------------------|---------------|-----------------------------|
| RBD material fracture | `rbd_material_fracture`, `rbd_concrete_fracture`, `rbd_glass_fracture`, `rbd_wood_fracture` | Sop | `rbdmaterialfracture`, `rbdconcretefracture`, `rbdglassfracture`, `rbdwoodfracture` |
| COps pyro | `pyro_configure`, `pyro_source_volume`, `pyro_block_begin`, `pyro_advect`, `pyro_buoyancy`, `pyro_turbulence`, `pyro_block_end` | Cop | `pyro_configure`, `pyro_sourcefromvolume`, `pyro_block_begin`, `pyro_vortexconfinement` |
| Sparse GPU pyro | `pyro_sparse_solver`, `smoke_sparse_object`, `smoke_sparse_solver`, `gas_opencl` | Dop | `pyrosolver_sparse`, `smokeobject_sparse`, `smokesolver_sparse`, `gasopencl` |
| rasterize Volume | `rasterize_volume`, `rasterize_setup`, `volume_rasterize`, `volume_rasterize_attributes` | Cop + Sop | `rasterizevolume`, `rasterizesetup`, `volumerasterize`, `volumerasterizeattributes` |

### Discover and author

1. `plan_modern_simulation()` → list the four families and their aliases.
2. `plan_modern_simulation(family="cops_pyro")` → deterministic, JSON-safe plan
   (node chain, real node types, parent categories, recommended parameters,
   required setup). Read-only; no `hou`, no cook, no scene mutation.
3. `create_modern_sim_node(parent_path=..., node_type="pyro_configure")`
   → resolve the alias, create the node in a parent network of the matching
   child category (`Sop`/`Cop`/`Dop`), apply bounded parameter overrides, and
   wire existing input nodes.

`plan_modern_simulation` always reports `artifact_verified=false` and
`simulation_verified=false`; `create_modern_sim_node` creates/wires only and
never cooks. Use the existing render or automation skills for an explicitly
requested cook, and verify any output artifact separately. Legacy COP2 networks
are not targeted: the Copernicus (`copnet`) context is `Cop`, and the sparse
GPU pyro chain is a DOP (`Dop`) network.
