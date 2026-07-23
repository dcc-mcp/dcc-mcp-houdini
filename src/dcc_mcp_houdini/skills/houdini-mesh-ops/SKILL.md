---
name: houdini-mesh-ops
description: >-
  Authoring skill — lightweight SOP mesh operations that append standard SOPs
  downstream of an input: transform, merge, blast/delete, group create, normals,
  triangulate, and convert. Each tool wires the new node into the network and
  returns its path for chaining. Use with houdini-geometry for inspection.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.68+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, sop, mesh, transform, merge, blast, group, normal, convert, authoring]
    search-hint: "transform merge blast delete group normals triangulate convert mesh sop edit"
    tools: tools.yaml
---

# houdini-mesh-ops

Typed mesh-edit tools that build procedural SOP networks. Every tool creates a
standard SOP downstream of the provided `input_path`, wires input 0, sets the
display flag, and returns the new node path so calls chain naturally.

All tools are `affinity: main` (they call `hou`).

## Tool group

- **`mesh-edit`:** `transform_geometry`, `merge_geometry`, `blast_geometry`
  (destructive), `group_geometry`, `add_normals`, `triangulate_geometry`,
  `convert_geometry`.

## Tracer-bullet flow

1. `houdini_geometry__create_primitive(parent_path="/obj/geo1", primitive="box")`
2. `transform_geometry(input_path=".../box1", translate=[2,0,0])`
3. `merge_geometry(input_paths=[".../xform1", ".../sphere1"])`
4. `add_normals(input_path=".../merge1")`
5. `houdini_geometry__get_cook_status(node_path=".../normal1")` → verify result

`blast_geometry` is flagged `destructive` because it removes geometry; pass
`delete_non_selected=true` to invert the selection (keep the group).
