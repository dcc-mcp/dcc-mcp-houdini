---
name: houdini-automation
description: >-
  Pipeline skill - run file-based Houdini Python automation, manage hip files,
  set timeline ranges, and build small node chains from structured specs. Use
  when orchestrating repeatable Houdini tasks. Not for inspecting a scene only.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: pipeline
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, automation, hip, timeline, pipeline, scripts]
    search-hint: "run python file, save hip, load hip, timeline, build node chain"
    tools: tools.yaml
---

# houdini-automation

Higher-level repeatable automation for Houdini sessions. Prefer `run_python_file`
for reviewed scripts on disk, and `build_node_chain` for compact graph recipes.
