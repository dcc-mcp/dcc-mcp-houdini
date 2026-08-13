---
name: houdini-groom
description: >-
  Authoring skill - build Houdini 22 short-fur groom networks from rest skin,
  optional guides, and animated skin. Use for insect fuzz, creature fur, and
  deformation-ready hair generation. Not for interactive brush sculpting.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 22.0+, dcc-mcp-core 0.19.70+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.1.0"
    tags: [houdini, groom, fur, hair, guides, insect, creature, deformation]
    search-hint: "insect fuzz bee fur hair generate guide deform animated skin groom"
    tools: tools.yaml
---

# Houdini groom

Build bounded native SOP networks for renderable short fur. All tools use main
thread affinity because they create and wire Houdini nodes.

## Workflow

1. Prepare a polygon rest skin and optional root-to-tip guides.
2. Call `build_short_fur_groom` with an optional animated skin. For anatomical
   variation, pass `region_profiles` such as `head`, `thorax`, and `abdomen`;
   each region may override its skin group, guides, density, length, segments,
   and clump strength.
3. Inspect the returned per-region Hair Generate/Clump nodes, shared Merge,
   and Guide Deform before rendering.

For insect fuzz, start with short lengths and Surface Deform. Use explicit
guides for directional thorax and abdomen hair.
