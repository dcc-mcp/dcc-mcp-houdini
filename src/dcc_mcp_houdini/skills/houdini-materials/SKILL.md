---
name: houdini-materials
description: >-
  Authoring skill - create Houdini material nodes and assign them to renderable
  nodes through typed HOM operations. Use when building lookdev/material
  workflows. Not for generic node graph edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, materials, lookdev, shader, assignment, authoring]
    search-hint: "create material, assign material, shader node, lookdev"
    tools: tools.yaml
---

# houdini-materials

Typed material authoring for Houdini scenes. Use `create_material` for material
network nodes and `assign_material` for renderable OBJ/SOP nodes with a material
path parameter.
