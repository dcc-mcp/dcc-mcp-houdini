---
name: houdini-simulation
description: >-
  Typed DOP simulation tools for Pyro, FLIP, RBD, and Vellum. Create a
  solver network, apply bounded parameters, inspect solver state, validate a
  setup before committing to a long cook, and build the fracture, constraint
  network and collision sources rigid-body work needs.
license: MIT
compatibility: "dcc-mcp-houdini 0.38+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, dop, simulation, pyro, flip, rbd, vellum, fracture, constraint, collision, solver, validation]
    search-hint: "pyro flip fluid rbd rigid vellum cloth grains dop solver simulation fracture glue collision cache validate"
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
| `create_constraint_network` | `constraintnetwork` (+ `glueconrel`, `softconrel`, `wireconrel`, `conetwistconrel`) | DOP level; sets `soppath` to the relationship SOP when the node exposes it |
| `create_collision_source` | `staticobject` | DOP level; sets `soppath` and attaches to the first solver input |

These three tools report unsupported parameters through `skipped_parameters`
instead of failing: node types and Houdini builds differ in which parameters
they expose, and a missing optional override is not an authoring error.

## Tracer-bullet flow

1. `create_simulation_network(parent_path="/obj", simulation_type="pyro")`
2. `configure_simulation_solver(solver_path="/obj/dopnet1/pyrosolver1", parameters={...})`
3. `inspect_simulation_network(network_path="/obj/dopnet1")`
4. `validate_simulation_setup(network_path="/obj/dopnet1", simulation_type="pyro")`
5. Supply the required object/source and output connections, then use the
   existing render or automation skills for an explicitly requested cook.

## Rigid-body flow

1. `create_fracture(parent_path="/obj/geo1", fracture_type="voronoi", source_path="/obj/geo1/box1")`
2. `create_simulation_network(parent_path="/obj", simulation_type="rbd")`
3. `create_constraint_network(dopnet_path="/obj/dopnet1", constraint_type="glue", relationship_parent="/obj/geo1")`
4. `create_collision_source(dopnet_path="/obj/dopnet1", source_path="/obj/geo1/ground1")`
5. `validate_simulation_setup(network_path="/obj/dopnet1", simulation_type="rbd")`

Particle (POP) authoring lives in the sibling `houdini-particles` skill.

Validation includes child errors and disconnected solvers. It reports its
structural scope and always leaves `simulation_verified=false`; a cached error
check cannot establish a successful simulation.

Parameters are checked before writing and read back after writing. Missing
parameters fail explicitly. Failed edits restore parameter values, expressions
and animation; failed creation removes only nodes owned by that request.
