---
name: houdini-mesh-ops
description: >-
  Authoring skill — typed procedural modeling operations with bounded schemas,
  native SOP parameter readback, and cooked geometry postconditions. Covers
  loft, lathe, extrude, bevel, inset, bridge, Boolean, edge-loop, radial array,
  mirror, UV, transform, merge, group, normal, triangulate, and convert flows.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.1.0"
    tags: [houdini, sop, mesh, modeling, loft, lathe, extrude, bevel, bridge, boolean, array, uv]
    search-hint: "typed houdini model loft lathe extrude bevel inset bridge boolean edge loop radial array mirror uv"
    tools: tools.yaml
    groups: groups.yaml
---

# houdini-mesh-ops

Typed modeling tools that build procedural SOP networks. Mutating tools use
bounded inputs and return parameter plus cooked-geometry readback. A tool fails
closed and removes its partial SOP when required native parameters, cooking, or
postconditions cannot be verified; there is no raw-script fallback.

All tools are `affinity: main` (they call `hou`).

## Tool group

- **`mesh-edit`** (default active): the existing transform/merge/group/normal/
  triangulate/convert tools; `blast_geometry` remains destructive.
- **`modeling`** (default inactive): `loft_sections`, `lathe_profile`,
  `extrude_faces`, `bevel_edges`, `inset`, `bridge_edges`, `boolean_op`,
  `add_edge_loop`, `array_instances` (bounded radial Copy to Points), `mirror`,
  `auto_uv`, and `uv_project`.

## Tracer-bullet flow

1. `houdini_geometry__create_primitive(parent_path="/obj/geo1", primitive="box")`
2. `bevel_edges(input_path=".../box1", group="0-3", distance=0.05)`
3. `array_instances(input_path=".../polybevel1", count=4, radius=3.5, axis="y")`
4. `auto_uv(input_path=".../copytopoints1")`
5. `houdini_geometry__get_cook_status(node_path=".../uvunwrap1")` → inspect again

`blast_geometry` is flagged `destructive` because it removes geometry; pass
`delete_non_selected=true` to invert the selection (keep the group).

Use `houdini-object-ops.set_pivot` for OBJ pivots and
`houdini-materials.assign_material` for material ownership. Houdini's procedural
SOP graph has no safe one-to-one `delete_history` operation; use the existing
explicit node-lock/export tools when a baked boundary is actually intended.
