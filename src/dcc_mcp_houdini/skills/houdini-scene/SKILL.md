---
name: houdini-scene
description: >-
  Scene skill — read-only inspection of the active Houdini hip file and node
  graphs. Use when you need frame range, hip path, object-level nodes, or node
  details. Not for creating geometry, sims, or exports — use authoring or
  interchange skills.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: scene
    version: "1.0.0"
    tags: [houdini, scene, hip, nodes, obj]
    search-hint: "scene info, hip file, list nodes, node details, obj context, frame range"
    tools: tools.yaml
---

# houdini-scene

Read-only scene inventory for agents. All tools are `affinity: main` because they call `hou`.

## Suggested flow

1. `get_scene_info` — hip path, playback range, /obj child count
2. `list_obj_nodes` or `list_child_nodes` — filter by node type when needed
3. `get_node_info` — inspect flags, child paths, and connections

On failure, load `houdini-scripting` and call `get_session_info`, or use gateway diagnostics when available.
