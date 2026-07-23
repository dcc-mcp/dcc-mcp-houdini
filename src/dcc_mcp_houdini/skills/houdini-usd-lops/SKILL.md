---
name: houdini-usd-lops
description: >-
  Solaris/USD query skill — read-only inspection of a LOP node's composed
  Stage. Use it to list prims, inspect one prim, or read bounded attribute
  values. Not for USD authoring, import, or export.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.68+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: interchange
    version: "1.0.0"
    tags: [houdini, solaris, usd, lops, stage, prims]
    search-hint: "inspect Solaris stage, list USD prims, prim info, USD attributes"
    search-aliases: [inspect usd stage, list lops prims, usd prim info, usd attributes, material binding]
    example-prompts:
      - "List the prims composed by /stage/karma1"
      - "Inspect /World/geo on the Stage from /stage/OUT"
      - "Show bounded attributes containing primvars on /World/geo"
    intent: "Inspect a composed Solaris USD Stage without authoring changes."
    recall-context:
      app_type: houdini
      domain: usd
      workflow-stage: interchange
      task-category: query
    requires: []
    produces: [usd_stage_report]
    preconditions:
      - type: software
        name: houdini
        version: ">=20.5"
    side-effects: {}
    tools: tools.yaml
---

# houdini-usd-lops

Read-only inspection of the composed USD Stage returned by a LOP node.

1. `list_stage_prims` for a bounded Stage inventory.
2. `get_prim_info` for type, state, visibility, transform, bounds, and material binding.
3. `get_prim_attributes` for filtered, size-bounded attribute values at a time code.

Load `houdini-interchange` instead when the task is file import or export.
