---
name: houdini-vdb
description: >-
  Typed VDB volume tools for Houdini. Create VDB SOPs, combine two grids in one
  call, and read back grid names, primitive counts and bounds from cached
  geometry without running a cook.
license: MIT
compatibility: "dcc-mcp-houdini 0.38+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, vdb, volume, sdf, fog, sdf, grid, sparse, convert, resample]
    search-hint: "vdb volume sdf fog grid sparse convert resample smooth combine clip advect inspect"
    tools: tools.yaml
---

# houdini-vdb

Typed VDB (sparse volume) authoring for Houdini's native volume SOPs. This is
the volumetric counterpart to `houdini-mesh-ops`: it covers the OpenVDB family
that the existing solver skills only reference indirectly through Pyro.

## Tracer-bullet flow

1. `create_vdb_node(parent_path="/obj/geo1", vdb_type="from_polygons", source_path="/obj/geo1/box1")`
2. `create_vdb_node(parent_path="/obj/geo1", vdb_type="smooth", source_path="/obj/geo1/vdbfrompolygons1")`
3. `combine_vdbs(parent_path="/obj/geo1", source_a_path="...", source_b_path="...")`
4. `inspect_vdb(node_path="/obj/geo1/vdbcombine1")`

Longer pipelines belong to `houdini_automation__build_node_chain`, which builds
and validates an arbitrary node recipe; this package stays focused on the
single-op calls an agent needs while iterating.

## Parameter policy

The tools create and wire nodes; they do not guess parameter values. SOP
parameters vary between Houdini releases, so an override the node does not
expose **fails the call and rolls back** rather than being silently skipped.
Pass what you want through `parameters` and read `applied_parameters` back.

Common `vdbcombine` operation values to pass through `parameters`:
`sdfunion`, `sdmintersect`, `sdfdifference`, `sdfblend`, `sum`, `product`,
`min`, `max`.

## Honesty contract

- `inspect_vdb` reports `geometry_available=false` instead of guessing when the
  node exposes no cached geometry.
- `volume_names` is populated from the `vdb_grids` intrinsic; an empty list
  means the read was not available, not that the volume is empty.
- Creation failures destroy only the nodes owned by the failed request, and
  parameter writes are rolled back (values, expressions and animation).
