---
name: houdini-materials
description: >-
  Authoring skill - create and assign Houdini materials, including typed
  MaterialX PBR networks for Karma. Use when building lookdev/material
  workflows from color, roughness, metallic, normal, or displacement maps. Not
  for generic node graph edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.19.68+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, materials, lookdev, shader, materialx, pbr, karma, displacement, assignment, authoring]
    search-hint: "create material, assign material, MaterialX PBR, Karma shader, texture maps, normal, displacement, lookdev"
    search-aliases: [create material, make shader, add material, assign material, set material, principled shader, materialx standard surface, pbr textures, karma material, normal map, displacement map, apply material to object]
    example-prompts:
      - "Create a red principled shader and assign it to /obj/geo1"
      - "Build a Karma MaterialX PBR material from color, roughness, normal, and displacement textures"
      - "Validate that /mat/planet has its MaterialX PBR channels connected"
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
path parameter. Use `build_materialx_pbr` for a complete MaterialX Builder with
standard-surface, normal-map, and displacement outputs, then call
`validate_materialx_pbr` before assignment or rendering.

`build_materialx_pbr` treats base color as color data and roughness, metallic,
normal, and displacement as raw data by default. It removes the newly created
subnet if any node or connection fails; it never replaces an existing material.
