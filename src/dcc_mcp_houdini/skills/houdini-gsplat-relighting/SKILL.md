---
name: houdini-gsplat-relighting
description: >-
  Houdini 22 Gaussian Splat relighting skill - prepare GSplats with SideFX
  Labs, relight them in Solaris/Karma, and rasterize them in Copernicus. Use
  when an agent must relight a captured splat while retaining typed scene and
  parameter control. Not for training or importing a new Gaussian Splat.
license: MIT
compatibility: "dcc-mcp-core 0.19.70+, Houdini 22.0+, SideFX Labs GSplat nodes"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: pipeline
    stage: pipeline
    tools: tools.yaml
    search-hint: >-
      Gaussian Splat GSplat relighting Labs normals delight albedo Solaris
      Karma shadow bias dome light Copernicus rasterize camera image refine
    tags: [houdini, gsplat, gaussian-splat, sidefx-labs, solaris, karma, copernicus]
---

# Gaussian Splat relighting

Use the typed tools in this package for the cross-context handoff:

1. Inspect the SOP output and confirm point attributes and provenance before
   changing it. A public reconstruction showcase requires splats trained from
   at least three views of the same subject with solved camera poses.
2. Prepare it with Labs `Normals from GSplats` and/or `Delight GSplats`.
3. In Solaris, use `Relight GSplats` with USD lights, a render camera, shadows,
   shadow bias, and optional dome/HDRI lighting. Use `houdini-parameters` for
   version-specific Labs parameters that are not exposed by the setup tool.
4. In Copernicus, import the prepared or relit SOP result and use `Rasterize
   GSplats` with camera metadata. The setup tool can append Sharpen, HSV,
   Gamma, and Premult nodes and set the H22 network resolution; use parameter
   skills for further interactive tuning.

The expected handoff attributes are `P`, `Cd` or `albedo`, `N`, `orient`,
`scale`/`pscale`, opacity, and optional `GS_SPH_R/G/B` plus `ao`. The setup
tools resolve Labs node type aliases at runtime because Labs asset namespaces
vary between Houdini 22 builds.

Procedural meshes sampled into points are synthetic point clouds, not captured
Gaussian Splat reconstructions. They may test relighting mechanics, but must not
be presented as reconstruction evidence or public GSplat showcase input.
