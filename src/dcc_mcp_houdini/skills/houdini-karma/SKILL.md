---
name: houdini-karma
description: >-
  Pipeline skill — configure Karma CPU/XPU render settings, material overrides,
  light mixer, and image output through typed tools. Pair with houdini-render
  for full render execution and houdini-camera-light for scene setup.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.68+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, karma, renderer, xpu, cpu, material, light_mixer, lookdev, pipeline]
    search-hint: "karma cpu xpu render samples denoise material override light mixer output exr"
    tools: tools.yaml
---

# houdini-karma

Typed Karma renderer configuration tools. All tools are `affinity: main`.
Parameter writes are defensive (multi-candidate parm names) to tolerate
Karma LOP, Karma ROP, and USD render product variants.

## Tool groups

- **`karma`:** `configure_karma` — engine (CPU/XPU), samples, noise threshold, denoise.
- **`material`:** `set_material_override` — global material override with presets
  (clay, gray, white, chrome, checker, normals, uv) or custom paths.
- **`light_mixer`:** `configure_light_mixer` — enable light mixer and adjust
  per-light intensity, exposure, and color.
- **`output`:** `set_image_output` — output path, format (exr/png/jpg/tif with
  bit depth), resolution, color space, layer name.

## Tracer-bullet flow

1. `configure_karma(node_path="/stage/karmarenderproduct1", device="xpu", pixel_samples=256, noise_threshold=0.01, denoise=true)`
2. `set_material_override(node_path="/stage/karmarenderproduct1", preset="clay")`
3. `configure_light_mixer(node_path="/stage/karmarenderproduct1", enable=true, lights=[{"name":"key_light","intensity":1.5},{"name":"rim_light","exposure":0.5}])`
4. `set_image_output(node_path="/stage/karmarenderproduct1", output_path="/tmp/render/beauty.$F4.exr", format="exr", resolution=[1920,1080], color_space="ACES - ACEScg")`
5. hand off to `houdini-render` (`render_rop`) for execution
