---
name: houdini-hda
description: >-
  HDA skill - install, inspect, create, cook, and save Houdini Digital Assets
  with typed parameters. Use when loading .hda/.otl assets or executing an HDA
  node as part of automation. Not for generic node edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, hda, otl, digital-asset, automation]
    search-hint: "install hda, load otl, execute hda, create hda node, save digital asset"
    tools: tools.yaml
---

# houdini-hda

Typed Houdini Digital Asset operations. `execute_hda` is the main high-level
entry point: it can install an asset file, instantiate a node, set parameters,
press button parms, and cook the node.
