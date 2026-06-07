---
name: houdini-materials
description: >-
  Authoring skill - create Houdini material nodes and assign them to renderable
  nodes through typed HOM operations. Use when building lookdev/material
  workflows. Not for generic node graph edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.18.9+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, materials, lookdev, shader, assignment, authoring]
    search-hint: "create material, assign material, shader node, lookdev"
    search-aliases: [create material, make shader, add material, assign material, set material, principled shader, apply material to object]
    example-prompts:
      - "Create a red principled shader and assign it to /obj/geo1"
      - "Make a new material in /mat"
      - "Assign the clay material to the selected object"
    intent: "Create Houdini material/shader nodes and assign them to renderable nodes."
    recall-context:
      app_type: houdini
      domain: lookdev
      workflow-stage: authoring
      task-category: mutate
    requires: []
    produces: [scene_node, material]
    preconditions:
      - type: software
        name: houdini
        version: ">=18.5"
    side-effects:
      creates: true
      modifies: true
      targets: [scene_node, material]
    tools: tools.yaml
---

# houdini-materials

Typed material authoring for Houdini scenes. Use `create_material` for material
network nodes and `assign_material` for renderable OBJ/SOP nodes with a material
path parameter.
