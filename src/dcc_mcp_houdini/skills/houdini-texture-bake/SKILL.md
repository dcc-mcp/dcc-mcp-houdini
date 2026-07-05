---
name: houdini-texture-bake
description: >-
  Pipeline stage — bake ambient occlusion, lighting, texture maps (diffuse,
  normals, cavity, curvature etc.) from geometry to image files, list
  bake-compatible geometry with UV info, and transfer maps from high-res source
  to low-res target. Pair with houdini-render for render output and
  houdini-materials for shader assignment.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 19.5+, dcc-mcp-core 0.19.9+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, bake, texture, ao, ambient-occlusion, lighting, normals, transfer-maps, maps-baker, cop, rop]
    search-hint: "bake texture map, ao ambient occlusion, normal map, transfer maps, high to low, lighting bake, texture baking, list bake targets"
    search-aliases: [bake textures, bake lighting, bake ambient occlusion, transfer maps, list bake targets]
    example-prompts:
      - "Bake ambient occlusion for all geometry in the scene"
      - "List all bake-compatible geometry with UV info"
      - "Bake diffuse and normal maps from /obj/high_res to /obj/low_res"
      - "Transfer normals and displacement from a high-poly source to a low-poly target"
      - "Bake lighting with Mantra at 2048 resolution"
    intent: "Bake textures (AO, lighting, normals, cavity, diffuse, custom maps), transfer maps between geometry, list bake targets."
    recall-context:
      app_type: houdini
      domain: pipeline
      workflow-stage: pipeline
      task-category: mutate
    requires: []
    produces: [baked_texture, image_file, transfer_map, bake_target_list]
    preconditions:
      - type: software
        name: houdini
        version: ">=19.5"
    side-effects:
      creates: true
      modifies: false
      targets: [texture, image, rop, cop]
    tools: tools.yaml
---

# houdini-texture-bake

Typed texture-baking tools that bake geometry attributes to image files using
Houdini's Bake Texture ROP, Labs Maps Baker, or COP-based fallback workflows.

## Bake method detection

Tools auto-detect the best available bake method at runtime:

1. **Labs Maps Baker** (`sidefx_labs` → `maps_baker`) — richest option,
   single-node multi-map bake with 20+ map types (normals, cavity, curvature,
   thickness, roughness, metallic, etc.)
2. **Bake Texture ROP** (`game_simple_baker` / `baker::2.0`) — built-in
   Houdini 20+ ROP for standard map baking
3. **COP fallback** — simple per-attribute COP-based bake when neither Labs
   nor Bake Texture ROP is available

When no bake method is detected, tools return a structured diagnostic payload
(`available_methods: [], recommendations: [...]`) — they never degrade to raw
`execute_python`.

## Tool groups

- **`bake-ao`:** `bake_ambient_occlusion` — bake ambient occlusion to texture
  (async, 900s timeout)
- **`bake-lighting`:** `bake_lighting` — bake scene lighting via Mantra/Karma
  render-to-texture (async, 900s timeout)
- **`bake-textures`:** `bake_textures` — general multi-map baking (diffuse,
  normals, cavity, curvature, roughness, metallic, etc.) via Labs Maps Baker
  or Bake Texture ROP (async, 1800s timeout)
- **`bake-query`:** `list_bake_targets` — scan geometry for UV-equipped,
  bake-compatible nodes (sync, read-only)
- **`bake-transfer`:** `transfer_maps` — transfer normals/displacement/diffuse
  from high-res source to low-res target (async, 1200s timeout)

## Context limitations

- **UV requirement:** Bake Texture ROP and Labs Maps Baker both require the
  target geometry to have non-degenerate UVs. `list_bake_targets` reports
  `has_uvs` so callers can verify before baking.
- **Renderer selection:** `bake_lighting` supports `mantra` (default) and
  `karma`. Karma requires a valid XPU/CPU license.
- **Labs Maps Baker:** Install via `sidefx_labs` package or Houdini Game Dev
  Toolset. Detection is automatic; tools report `labs_maps_baker_available`
  in their result payload.

## Tracer-bullet flow

1. `list_bake_targets()` → scan geometry, pick nodes with UVs
2. `bake_ambient_occlusion(rop_path="/out/bake_ao", objects=["/obj/sphere"])`
3. `bake_textures(rop_path="/out/bake_maps", objects=["/obj/character"], map_types=["normals", "cavity", "diffuse"])`
4. `bake_lighting(rop_path="/out/bake_light", camera="/obj/rendercam", objects=["/obj/building"])`
5. `transfer_maps(source="/obj/high_res", target="/obj/low_res", map_types=["normals", "displacement"])`
