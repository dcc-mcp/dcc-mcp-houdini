---
name: houdini-render
description: >-
  Pipeline skill — viewport capture/flipbook plus ROP render settings and
  render execution through typed, runtime-aware tools. Exports report
  written_files, elapsed time, and warnings without hanging the host. Pair with
  houdini-camera-light to set up cameras and lights first.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.18.9+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, render, rop, karma, mantra, viewport, flipbook, capture, pipeline]
    search-hint: "render rop karma mantra viewport capture flipbook screenshot render settings resolution output"
    tools: tools.yaml
---

# houdini-render

Typed render and visual-verification tools. All tools are `affinity: main`.
Viewport tools are **UI-aware**: in a headless `hython` session they return a
structured `warnings` payload with `captured: false` instead of failing, so an
agent can detect and skip cleanly when rendering is unavailable.

## Tool groups

- **`viewport`:** `capture_viewport` (single frame), `flipbook` (range). Both
  clamp resolution to 4096 and return `written_files` / `skipped` / `warnings`.
- **`render`:** `get_render_settings` (read-only), `set_render_settings`
  (reports `unsupported` fields per ROP type), `render_rop` (async, long
  timeout, reports `elapsed_secs` + `written_files`).

## Tracer-bullet flow

1. `houdini_camera_light__create_camera(name="rendercam")`
2. `set_render_settings(rop_path="/out/mantra1", camera="/obj/rendercam", resolution=[1280,720], output_path="/tmp/beauty.exr")`
3. `get_render_settings("/out/mantra1")` → verify
4. `capture_viewport(output_path="/tmp/preview.jpg")` for a quick look (UI only)
5. `render_rop("/out/mantra1", frame_range=[1,1])` → `written_files`, `elapsed_secs`

`render_rop` is `async` with a 30-minute timeout hint; output-path and
resolution parameter writes are defensive (candidate names) so Mantra, Karma,
and ROP geometry/USD drivers are all tolerated.
