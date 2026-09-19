---
name: houdini-texture-bake
description: >-
  Pipeline stage — bake ambient occlusion, lighting, texture maps (diffuse,
  normals, cavity, curvature etc.) from geometry to image files, list
  bake-compatible geometry with UV and UDIM info, configure multi-tile UDIM
  output, verify baked files landed, and transfer maps from high-res source
  to low-res target. Pair with houdini-render for render output and
  houdini-materials for shader assignment.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 19.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, bake, texture, ao, ambient-occlusion, lighting, normals, transfer-maps, maps-baker, cop, rop, udim]
    search-hint: "bake texture map, ao ambient occlusion, normal map, transfer maps, high to low, lighting bake, texture baking, list bake targets, udim tile output verify"
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
- **`bake-setup`:** `configure_udim_bake` — configure a bake output for UDIM
  tiles (sync)
- **`bake-transfer`:** `transfer_maps` — transfer normals/displacement/diffuse
  from high-res source to low-res target (async, 1200s timeout)
- **`bake-verify`:** `inspect_bake_output` — verify baked files exist on disk,
  expanding the UDIM token and naming missing tiles (sync, read-only)

## UDIM support

`list_bake_targets` reports UDIM coverage per target in the same terms
`houdini_uv__inspect_uv` uses, so the two packages agree on what a tile is:

| Field | Meaning |
|---|---|
| `udim_tiles` | Tile indices computed as `1001 + floor(u) + 10 * floor(v)` |
| `udim_tile_count` | Number of distinct tiles |
| `udim_detection` | `computed`, `no_values`, `no_uv_sets` or `unavailable` |
| `needs_udim_output` | True when the geometry spans more than one tile |
| `geometry_available` | False when the node is dirty or exposes no cached geometry |


When `needs_udim_output` is true, a flat output path silently collapses every
tile into one file. Use `configure_udim_bake` before baking: it resolves the
tile set (from `target_path` geometry, or an explicit `tile_range`), inserts the
`%(UDIM)d` token into the output path when it is missing, and returns the
concrete per-tile paths. After the bake, `inspect_bake_output` expands the
token, globs the result and names any tile from `expected_tiles` that is
missing.

A tile count of 1 is not an error: `needs_udim_output` stays false and the
output path is left flat.

UDIM coverage is resolved **before** any geometry read. A dirty node reports
`geometry_available=false`, `udim_detection=unavailable`, `primitive_count=0`
and `bake_ready=false` instead of being cooked implicitly — cook it first, then
inspect. `configure_udim_bake` resolves the tile set before creating a ROP, and
destroys a ROP it created if a later step fails. A pre-existing ROP is not
destroyed, so its parameter writes run as one transaction: every parameter name
is validated before anything is written, and a write that fails part-way rolls
the ROP back to the values it had on entry.

`uv_layers`, `has_uvs` and `bake_ready` come from the same UV convention as
`udim_detection` — vertex attributes first, name anchored at the start — so a
payload can never claim `bake_ready=true` next to `udim_detection=no_uv_sets`.
Attributes such as `Cd_uv` or `flowuv` are not UV sets.

## Context limitations

- **UV requirement:** Bake Texture ROP and Labs Maps Baker both require the
  target geometry to have non-degenerate UVs. `list_bake_targets` reports
  `has_uvs` so callers can verify before baking.
- **UDIM requires explicit configuration:** the bake writers do not infer tile
  layout from the geometry, so `configure_udim_bake` must run before a
  multi-tile bake.
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

## UDIM flow

1. `list_bake_targets()` → pick targets whose `needs_udim_output` is true
2. `configure_udim_bake(rop_path="/out/bake_maps", target_path="/obj/character", output_path="/tmp/hero.exr")`
   → reports `output_paths` such as `/tmp/hero.1001.exr`, `/tmp/hero.1002.exr`
3. bake with the existing bake tools
4. `inspect_bake_output(output_path="/tmp/hero.%(UDIM)d.exr", expected_tiles=[1001, 1002])`

`configure_udim_bake` reports `skipped_parameters` for the defaults it could
not seed (bake writers differ in which parameters they expose); caller-supplied
`parameters` are strict and fail the call on an unknown name.
