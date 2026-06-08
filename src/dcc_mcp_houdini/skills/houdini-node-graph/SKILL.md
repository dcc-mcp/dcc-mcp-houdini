---
name: houdini-node-graph
description: >-
  Authoring skill — inspect and edit Houdini node-graph relationships: list
  inputs/outputs/dependents and connect or disconnect inputs by explicit index.
  Use instead of arbitrary Python for wiring nodes. For parameters/expressions
  use houdini-parameters; for creating nodes use houdini-nodes.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.18.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, graph, connections, inputs, outputs, wiring, authoring]
    search-hint: "node connections, inputs outputs, connect input, disconnect, dependencies, downstream consumers"
    tools: tools.yaml
---

# houdini-node-graph

Typed node-graph relationship tools for agents. All tools are `affinity: main`
because they call `hou`. Prefer these over
`houdini-scripting.execute_python` for inspecting and wiring connections.

## Tool groups

- **`graph-query`** (read-only): `get_connections` — inputs, outputs, dependents.
- **`graph-edit`** (mutating): `connect_input`, `disconnect_input` — explicit
  input/output indexes with structured failures.

## Suggested flow

1. `get_connections` to understand current wiring
2. `connect_input` / `disconnect_input` to rewire by index

For parameter edits use `houdini-parameters`; for node creation use
`houdini-nodes`.
