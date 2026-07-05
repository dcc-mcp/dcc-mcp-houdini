---
name: houdini-automation
description: >-
  Pipeline skill - run file-based Houdini Python automation, manage hip files,
  set timeline ranges, and build small node chains from structured specs. Use
  when orchestrating repeatable Houdini tasks. Not for inspecting a scene only.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.19.9+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: pipeline
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, automation, hip, timeline, pipeline, scripts]
    search-hint: "run python file, save hip, load hip, timeline, build node chain"
    search-aliases: [run script file, save hip, open hip, load scene, set frame range, timeline, build node chain, automate houdini]
    example-prompts:
      - "Run this Python file in Houdini"
      - "Save the hip file to /projects/showA/shot.hip"
      - "Set the frame range to 1-120 and build a box→transform chain"
    intent: "Run repeatable file-based Houdini automation: scripts, hip I/O, timeline, and node-chain recipes."
    recall-context:
      app_type: houdini
      domain: pipeline
      workflow-stage: pipeline
      task-category: mutate
    requires: []
    produces: [scene_state, node_network, "file:hip"]
    preconditions:
      - type: software
        name: houdini
        version: ">=18.5"
    side-effects:
      creates: true
      modifies: true
      file-output: true
      targets: [scene_state, node_network, "file:hip"]
    tools: tools.yaml
---

# houdini-automation

Higher-level repeatable automation for Houdini sessions. Prefer `run_python_file`
for reviewed scripts on disk, and `build_node_chain` for compact graph recipes.
