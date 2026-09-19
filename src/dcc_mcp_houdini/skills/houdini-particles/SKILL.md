---
name: houdini-particles
description: >-
  Typed POP (particle operator) tools for Houdini. Create a POP network
  skeleton, configure sources, attach forces and behaviors, and read back
  particle counts, attributes and bounds without running a cook.
license: MIT
compatibility: "dcc-mcp-houdini 0.38+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, pop, particles, dop, forces, points, simulation, validation]
    search-hint: "particles pop popnet points forces wind drag vortex kill replicate sprite inspection"
    tools: tools.yaml
---

# houdini-particles

Typed POP authoring for Houdini's native particle operators. The package
complements `houdini-simulation`: that skill builds a DOP solver skeleton for
Pyro, FLIP, RBD and Vellum, while this one covers the POP family (points,
sprites, particle fluids) that has no typed coverage elsewhere in the adapter.

## Tracer-bullet flow

1. `create_pop_network(parent_path="/obj")` → popnet + popsolver + popobject +
   popsource, with the solver's object input wired.
2. `configure_pop_source(node_path="/obj/popnet1/popsource1", parameters={...})`
3. `add_particle_force(network_path="/obj/popnet1", force_type="wind")`
4. `add_particle_behavior(network_path="/obj/popnet1", behavior_type="kill")`
5. `inspect_particles(node_path="/obj/popnet1/popobject1")` → counts and
   attributes from cached geometry.

## Wiring contract

POP micro-solvers attach to the inputs of the network's `popsolver`. With no
`connect_to`, a force or behavior node is created and attached to the first
free input of the first `popsolver` found in the network; when no solver
exists the node is left unattached and reported with
`setup_state="unattached"`, so the caller can wire it explicitly. Pass an
explicit `connect_to` path when the automatic target is not the node you want.

## Honesty contract

- `create_pop_network` returns `setup_state="skeleton"` and never claims
  `simulation_verified=true`; source geometry, POP chain wiring and a cook are
  still required.
- `inspect_particles` reports `geometry_available=false` instead of guessing
  when the node exposes no cached geometry.
- Parameter overrides never fail silently: a name the target node does not
  expose fails the call and rolls the edit back, so a mistyped override can
  never leave a caller believing it took effect. This package has no
  `skipped_parameters` field and does not skip unsupported overrides.
- Failed creation destroys only the nodes owned by that request.
