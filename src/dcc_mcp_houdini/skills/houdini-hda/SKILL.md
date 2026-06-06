---
name: houdini-hda
description: >-
  HDA skill - install, inspect, create, cook, and save Houdini Digital Assets
  with typed parameters. Use when loading .hda/.otl assets or executing an HDA
  node as part of automation. Not for generic node edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.18.7+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, hda, otl, digital-asset, automation]
    search-hint: "install hda, load otl, execute hda, create hda node, save digital asset"
    search-aliases: [use hda, install hda, load otl, run digital asset, instantiate hda, execute hda, save hda, create digital asset]
    example-prompts:
      - "Install this .hda file and run the asset"
      - "Use the labs::my_asset HDA under /obj with these parameters"
      - "Save /obj/geo1 as a digital asset"
    intent: "Install, inspect, instantiate, cook, and save Houdini Digital Assets."
    recall-context:
      app_type: houdini
      domain: assets
      workflow-stage: authoring
      task-category: mutate
    requires: []
    produces: [scene_node, file:hda]
    preconditions:
      - type: software
        name: houdini
        version: ">=18.5"
    side-effects:
      creates: true
      modifies: true
      file-output: true
      targets: [scene_node, file:hda]
    tools: tools.yaml
---

# houdini-hda

Typed Houdini Digital Asset operations. `execute_hda` is the main high-level
entry point: it can install an asset file, instantiate a node, set parameters,
press button parms, and cook the node.
