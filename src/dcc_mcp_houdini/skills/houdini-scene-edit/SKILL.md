---
name: houdini-scene-edit
description: >-
  Scene-management skill — typed Houdini scene lifecycle (new/open/save with
  dirty-scene safeguards), selection (get/set/find), camera discovery, and
  bounding-box queries. Use these atomic tools instead of arbitrary Python for
  everyday scene navigation and file operations. Not for node authoring (use
  houdini-nodes) or geometry/transform edits (use houdini-object-ops).
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.18.34+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: scene
    version: "1.0.0"
    tags: [houdini, scene, hip, selection, camera, bounds]
    search-hint: "new scene, open hip, save hip, get selection, set selection, find nodes, list cameras, bounding box"
    tools: tools.yaml
---

# houdini-scene-edit

Typed scene-management tools for agents. All tools are `affinity: main` because
they call `hou`. Prefer these over `houdini-scripting.execute_python` for scene
lifecycle and navigation.

## When to use

- **Lifecycle:** `new_scene`, `open_scene`, `save_scene` — each guards against
  silently discarding unsaved changes (pass `force=true` to override).
- **Selection & discovery:** `get_selection`, `set_selection`, `find_nodes`,
  `list_cameras`, `get_bounding_box`.

## Suggested flow

1. `find_nodes` (by name glob or type substring) → `set_selection`
2. `get_bounding_box` to frame or measure a result
3. `save_scene` to persist

For node creation/connection use `houdini-nodes`; for rename/parent/flags and
transforms use `houdini-object-ops`. On failure, load `houdini-scripting` and
call `get_session_info`, or use gateway diagnostics when available.
