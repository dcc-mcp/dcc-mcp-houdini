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
   changing it. The preflight recognizes Houdini-native GSplats and standard
   3DGS PLY exports (`f_dc*`, `rot*`, `scale*`, `opacity`, and `f_rest*`). A
   public reconstruction showcase requires splats trained from at least three
   views of the same subject with solved camera poses.
2. Prepare it with Houdini `Bake GSplats` when normalization is required, then
   Labs `Normals from GSplats` and/or `Delight GSplats`. Keep spherical
   harmonics enabled when the source provides `f_rest*` coefficients.
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

## Trained checkpoint and subject-cleanup contract

When the source is a trained Nerfstudio `splatfacto` checkpoint, preserve the
actual Gaussian tensors: `means`, `scales`, `quats`, `opacities`,
`features_dc`, and `features_rest`. Export SH-rest coefficients in the Inria
PLY order (channel-major after transposing coefficient/channel axes), and keep
the training step plus checkpoint digest in the reconstruction manifest. A
dense or high-polygon proxy is not equivalent evidence.

Specimen and turntable captures commonly fit black-background Gaussians around
the subject. Cleanup must be deterministic and disclosed. Prefer this bounded
sequence:

1. fit and remove known capture fixtures such as a specimen pin;
2. derive a robust subject support volume from non-background Gaussians;
3. retain dark anatomy only when it is spatially supported by nearby subject
   Gaussians;
4. reject oversized dark splats outside the expected anatomical scale;
5. record source/kept/removed counts and cleanup thresholds.

Fixture cleanup is not accepted from a distant beauty frame alone. Validate
the cleaned splat from at least two source-camera projections and one novel
view, and explicitly inspect the fitted fixture region for coherent residual
clusters. Colored rings, labels, mounting wire, or pin fragments that remain
spatially disconnected from anatomy are a failed cleanup, even when the
overall silhouette is recognizable. Keep the result as engineering evidence
until those residuals are removed; do not promote it to a public beauty asset.

Do not use a global luminance threshold as a downstream `bee_mask` or subject
mask. It removes black compound eyes, dark thorax regions, antennae, and legs,
and produces a bright hollow silhouette even when the trained splat is valid.
Validate dark-anatomy retention and background rejection separately.

The published reconstruction bundle must keep camera provenance, finite-array
checks, bounds, Gaussian counts, hashes, and fresh holdout metrics. Never reuse
PSNR/SSIM/LPIPS from a different checkpoint; mark those metrics pending until
the matching checkpoint is rendered and evaluated.

For animated splats, verify that deformation preserves `orient`, anisotropic
`scale`, opacity, and SH attributes in addition to `P`. A point-position-only
deformation can appear plausible in a point preview while producing incorrect
ellipsoid orientation in a real GSplat rasterizer.
