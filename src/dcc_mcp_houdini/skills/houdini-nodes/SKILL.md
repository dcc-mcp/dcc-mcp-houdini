---
name: houdini-nodes
description: >-
  Authoring skill - create, connect, configure, cook, lay out, and delete
  Houdini nodes through typed HOM operations. Use when building SOP/OBJ/ROP
  networks or automating graph edits. Not for arbitrary Python snippets.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, nodes, hom, sop, obj, authoring]
    search-hint: "create node, connect nodes, set parms, cook node, layout network"
    tools: tools.yaml
---

# houdini-nodes

Typed HOM node-graph operations for agents. Prefer these tools before using
`houdini-scripting.execute_python`.

## Common Flow

1. `create_node`
2. `set_node_parms`
3. `connect_nodes`
4. `cook_node`
5. `layout_children`
