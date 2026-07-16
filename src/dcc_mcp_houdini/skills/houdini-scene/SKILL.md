---
name: houdini-scene
description: >-
  Scene skill — read-only inspection of the active Houdini hip file and node
  graphs. Use when you need frame range, hip path, object-level nodes, or node
  details. Not for creating geometry, sims, or exports — use authoring or
  interchange skills.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.33+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: scene
    version: "1.0.0"
    tags: [houdini, scene, hip, nodes, obj]
    search-hint: "scene info, hip file, list nodes, node details, obj context, frame range"
    search-aliases: [scene summary, what is in the scene, list nodes, find nodes, hip info, frame range, inspect node, node connections, obj tree]
    example-prompts:
      - "What's in the current Houdini scene?"
      - "List all geo nodes under /obj"
      - "Show the inputs and outputs of /obj/geo1"
    intent: "Inspect the active hip file and node graph without modifying anything."
    recall-context:
      app_type: houdini
      domain: scene
      workflow-stage: scene
      task-category: query
    requires: []
    produces: [scene_report]
    preconditions:
      - type: software
        name: houdini
        version: ">=18.5"
    side-effects: {}
    tools: tools.yaml
---

# houdini-scene

Read-only scene inventory for agents. All tools are `affinity: main` because they call `hou`.

## Suggested flow

1. `get_scene_info` — hip path, playback range, /obj child count
2. `list_obj_nodes` or `list_child_nodes` — filter by node type when needed
3. `get_node_info` — inspect flags, child paths, and connections

On failure, load `houdini-scripting` and call `get_session_info`, or use gateway diagnostics when available.
