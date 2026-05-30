---
name: houdini-scripting
description: >-
  Bootstrap skill — controlled Python execution inside Houdini's hython
  interpreter. Use when no typed Houdini skill covers the task or you need
  session diagnostics. Not for routine scene edits — prefer houdini-scene or
  future domain skills.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: thin-harness
    stage: bootstrap
    version: "1.0.0"
    tags: [houdini, scripting, python, automation, bootstrap]
    search-hint: "execute python, run script, hython, hou, session info"
    search-aliases: [run python, execute code, hython script, run hou code, arbitrary script, session info, houdini version, escape hatch]
    example-prompts:
      - "Run this Python snippet in Houdini"
      - "What Houdini version and hip file is loaded?"
      - "Execute a one-off hou script"
    intent: "Run arbitrary Python in Houdini when no typed skill fits, or read session diagnostics."
    recall-context:
      app_type: houdini
      domain: scripting
      workflow-stage: bootstrap
      task-category: mutate
    requires: []
    produces: [scene_state]
    preconditions:
      - type: software
        name: houdini
        version: ">=18.5"
    side-effects:
      creates: true
      modifies: true
      deletes: true
      ui-mutation: true
      targets: [scene_state, scene_node]
    tools: tools.yaml
---

# houdini-scripting

Escape hatch for arbitrary Python in Houdini. **Skills-first:** call typed tools from other skills before `execute_python`.

## When to use

- Confirm Houdini version, hip path, and UI availability → `get_session_info`
- One-off automation with no typed tool yet → `execute_python`

## Safety

- All tools run on the main thread (`affinity: main`).
- `execute_python` can mutate the scene; treat as destructive.
