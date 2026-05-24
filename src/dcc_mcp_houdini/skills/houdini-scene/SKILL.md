---
name: houdini-scene
description: >-
  Scene skill — read-only inspection of the active Houdini hip file and /obj node
  graph. Use when you need frame range, hip path, or object-level nodes. Not for
  creating geometry, sims, or exports — use future authoring/interchange skills.
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
    search-hint: "scene info, hip file, list nodes, obj context, frame range"
    tools: tools.yaml
---

# houdini-scene

Read-only scene inventory for agents. All tools are `affinity: main` because they call `hou`.

## Suggested flow

1. `get_scene_info` — hip path, playback range, /obj child count
2. `list_obj_nodes` — filter by node type when needed

On failure, load `houdini-scripting` and call `get_session_info`, or use gateway diagnostics when available.
