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
    search-aliases: [create sop node, add node, make node, build network, wire nodes, connect inputs, set parameters, cook node, delete node, layout graph]
    example-prompts:
      - "Create a box SOP under /obj/geo1"
      - "Wire the transform into the merge node"
      - "Set the radius parameter on the sphere and cook it"
    intent: "Build and edit Houdini node networks (SOP/OBJ/ROP) through typed HOM operations."
    recall-context:
      app_type: houdini
      domain: modeling
      workflow-stage: authoring
      task-category: mutate
    requires: []
    produces: [scene_node, node_network]
    preconditions:
      - type: software
        name: houdini
        version: ">=18.5"
    side-effects:
      creates: true
      modifies: true
      deletes: true
      targets: [scene_node, node_network]
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
