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
