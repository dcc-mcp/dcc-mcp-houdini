---
name: houdini-render
description: >-
  Pipeline skill — viewport capture/flipbook plus ROP render settings and
  render execution through typed, runtime-aware tools. Exports report
  written_files, elapsed time, and warnings without hanging the host. Pair with
  houdini-camera-light to set up cameras and lights first.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.33+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, render, rop, karma, mantra, viewport, flipbook, capture, pipeline, aov, render_layer, takes]
    search-hint: "render rop karma mantra viewport capture flipbook screenshot render settings resolution output aov render layer takes stats"
    tools: tools.yaml
---

# houdini-render

Typed render and visual-verification tools. Scene inspection and launch tools
use `affinity: main`; background job polling and cancellation use `affinity: any`.
Viewport tools are **UI-aware**: in a headless `hython` session they return a
structured `warnings` payload with `captured: false` instead of failing, so an
agent can detect and skip cleanly when rendering is unavailable.

## Tool groups

- **`viewport`:** `capture_viewport` (single frame), `flipbook` (range). Both
  clamp resolution to 4096 and return `written_files` / `skipped` / `warnings`.
- **`render`:** `get_render_settings` (read-only), `set_render_settings`
  (reports `unsupported` fields per ROP type), `render_rop` (foreground or
  isolated `hython` background job), `get_render_job` (polls and reconciles
  status without blocking the UI), `cancel_render_job` (cancels only jobs
  owned by the current adapter process), `configure_aovs` (add/remove
  AOVs with 15+ presets), `get_render_stats` (read resolution/samples/renderer/output).
- **`render_layer`:** `create_render_layer` (Solaris RenderProduct or ROP merge),
  `manage_takes` (create/switch/delete/list takes for render layer variants).

## Tracer-bullet flow

### Viewport/Render

1. `houdini_camera_light__create_camera(name="rendercam")`
2. `set_render_settings(rop_path="/out/mantra1", camera="/obj/rendercam", resolution=[1280,720], output_path="/tmp/beauty.exr")`
3. `get_render_settings("/out/mantra1")` → verify
4. `capture_viewport(output_path="/tmp/preview.jpg")` for a quick look (UI only)
5. `render_rop("/out/mantra1", frame_range=[1,1])` → background `job_id` in interactive Houdini; foreground results in headless Houdini

### Render Layers & AOVs

1. `create_render_layer(name="beauty", parent_path="/stage", purpose="beauty", aovs=["diffuse","specular","normal","depth"])`
2. `configure_aovs(rop_path="/stage/beauty", aovs=["motionvector","cryptomatte"], action="add")`
3. `get_render_stats(rop_path="/stage/beauty")` → verify resolution/samples/output

### Takes

1. `manage_takes(action="create", take_name="lighting_variant_a")`
2. `manage_takes(action="switch", take_name="lighting_variant_a")`
3. `manage_takes(action="list")` → review all takes

Interactive Houdini defaults to an isolated process; poll
`get_render_job(job_id)` and use `cancel_render_job(job_id)` to stop a job
started by the same adapter process. Pass `background=false` only when
foreground execution is intentional. Headless Houdini defaults to foreground execution.
The default poll response is bounded: it reports `completed`, `total`,
fractional `progress`, `elapsed_secs`, `eta_secs`, `written_file_count`, and up
to ten `recent_written_files`. `output_verification.state` distinguishes
`verified`, `not_observed`, and `unavailable` output evidence. Pass
`include_details=true` only when the full
expected-output snapshot, complete written-file and warning lists, error, and
traceback are needed. The same job lifecycle also observes `cache_simulation` and
`execute_rop_chain` jobs.
ROP-chain completion is governed by execution/cook errors; a chain without a
discoverable output pattern can complete with `output_verification.state` set
to `unavailable`. Render and cache jobs still require a new or updated output.
Interactive background launch requires a saved HIP with no unsaved changes and
never auto-saves the GUI scene. Headless Houdini defaults to foreground; when
`background=true` is explicitly requested, the adapter requires an existing HIP
and saves its current state before spawning the isolated worker.
The main thread only validates the ROP and launches the isolated process;
Mantra/Karma work never occupies Houdini's event loop. Output-path and
resolution parameter writes are defensive (candidate names) so Mantra, Karma,
and ROP geometry/USD drivers are all tolerated.
