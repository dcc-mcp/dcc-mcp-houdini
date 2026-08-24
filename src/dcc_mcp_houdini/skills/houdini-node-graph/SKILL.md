---
name: houdini-node-graph
description: >-
  Authoring skill — inspect and edit Houdini node-graph relationships: semantic
  network inspection (broken inputs, orphans, cycles, subgraphs, type mismatches),
  controllable auto-layout with user-position preservation, connect/disconnect
  inputs by explicit index. Use instead of arbitrary Python for wiring nodes.
  For parameters/expressions use houdini-parameters; for creating nodes use
  houdini-nodes.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.91+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.1.0"
    tags: [houdini, graph, connections, inspection, layout, semantic, authoring]
    search-hint: "node connections, network inspection, broken inputs, orphans, cycles, auto layout, user layout preservation, semantic analysis"
    tools: tools.yaml
---

# houdini-node-graph

Typed node-graph relationship tools for agents. All tools are `affinity: main`
because they call `hou`. Prefer these over
`houdini-scripting.execute_python` for inspecting and wiring connections.

## Tool groups

- **`graph-inspect`** (read-only): `inspect_network` — full semantic analysis
  of a parent network: broken inputs, orphaned nodes, cycles, disconnected
  subgraphs, type-mismatched connections, chain roots and ends.
- **`graph-query`** (read-only): `get_connections` — inputs, outputs, dependents.
- **`graph-edit`** (mutating): `connect_input`, `disconnect_input` — explicit
  input/output indexes with structured failures.
- **`graph-layout`** (mutating): `auto_layout` — controllable auto-layout with
  user-position preservation. Two strategies: `houdini_default` and
  `tree_left_to_right`. Supports `dry_run` for preview and
  `preserve_user_layout` to skip user-touched nodes.

## Suggested flows

### Semantic inspection
1. `inspect_network("/obj/geo1")` — get the full health picture
2. Diagnose: broken inputs → missing connections, orphaned nodes → unused generators,
   cycles → feedback loops, subgraphs > 1 → fragmented network
3. Fix with `connect_input` / `disconnect_input`

### Auto-layout with user preservation
1. `auto_layout(parent_path="/obj/geo1", dry_run=true)` — preview what will move
2. Confirm the plan: `preserved_paths` contains user-touched nodes left untouched
3. `auto_layout(parent_path="/obj/geo1")` — apply layout, preserving user positions
4. Optionally switch strategy: `auto_layout(parent_path="/obj/geo1", strategy="tree_left_to_right")`

For parameter edits use `houdini-parameters`; for node creation use
`houdini-nodes`.
