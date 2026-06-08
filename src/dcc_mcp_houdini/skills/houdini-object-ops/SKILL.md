---
name: houdini-object-ops
description: >-
  Authoring skill — object-level Houdini mutations: rename, duplicate, reparent,
  set display/render/template/bypass flags, hard-lock/unlock, and read/set
  translate-rotate-scale transforms. Use these typed tools instead of arbitrary
  Python for editing existing nodes. Not for creating nodes (use houdini-nodes)
  or scene lifecycle/selection (use houdini-scene-edit).
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.18.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, object, transform, rename, parent, flags, authoring]
    search-hint: "rename node, duplicate node, reparent, move node, set flags, lock node, get transform, set transform, translate rotate scale"
    tools: tools.yaml
---

# houdini-object-ops

Typed object-level edit tools for agents. All tools are `affinity: main` because
they call `hou`. Prefer these over `houdini-scripting.execute_python` when
editing nodes that already exist.

## Tool groups

- **`object-edit`:** `rename_node`, `duplicate_node`, `parent_node`,
  `set_node_flags`, `set_node_lock`.
- **`object-transform`:** `get_transform`, `set_transform` (operate on OBJ-level
  `t`/`r`/`s` parm tuples).

## Suggested flow

1. Find/select with `houdini-scene-edit` (`find_nodes` → `set_selection`)
2. `get_transform` → `set_transform` to position an object
3. `set_node_flags` / `set_node_lock` to control display and freeze state

For creating new nodes use `houdini-nodes`. On failure, load `houdini-scripting`
and call `get_session_info`, or use gateway diagnostics when available.
