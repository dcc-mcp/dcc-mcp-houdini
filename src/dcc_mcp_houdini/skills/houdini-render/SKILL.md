---
name: houdini-render
description: >-
  Pipeline skill — viewport capture/flipbook plus ROP render settings and
  render execution through typed, runtime-aware tools. Exports report
  written_files, elapsed time, and separate error/warning diagnostics without
  hanging the host. Pair with
  houdini-camera-light to set up cameras and lights first.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.1"
    tags: [houdini, render, rop, karma, mantra, viewport, flipbook, capture, pipeline, aov, render_layer, takes, denoise, oidn]
    search-hint: "render rop karma mantra viewport capture flipbook screenshot render settings resolution output aov render layer takes stats denoise idenoise oidn optix exr"
    tools: tools.yaml
---

# houdini-render

Typed render and visual-verification tools. Scene inspection and launch tools
use `affinity: main`; background job polling and cancellation use `affinity: any`.
Viewport tools are **UI-aware**: in a headless `hython` session they return a
structured `warnings` payload with `captured: false` instead of failing, so an
agent can detect and skip cleanly when rendering is unavailable.
OpenGL ROP rendering is likewise rejected in headless Houdini because the
native viewport/Vulkan path may terminate the process; use interactive Houdini
or Karma/Husk for batch rendering.

## Tool groups

- **`viewport`:** `capture_viewport` (single frame), `flipbook` (range with an
  optional positive increment and explicit camera). Both clamp resolution to
  4096 and return `written_files` / `skipped` / `warnings`.
- **`render`:** `get_render_settings` (read-only), `set_render_settings`
  (reports `unsupported` fields per ROP type), `render_rop` (foreground or
  isolated `hython` background job), `get_render_job` (polls and reconciles
  status without blocking the UI), `finalize_render_outputs` (publishes
  externally validated staged EXRs without replacing finals), `cancel_render_job` (cancels only jobs
  owned by the current adapter process), `configure_aovs` (add/remove Solaris
  RenderVars or native Mantra auxiliary planes with renderer-correct processing),
  `denoise_image` (official OIDN/OptiX EXR postprocess with source preservation
  and no-clobber output publication),
  `validate_karma_stage` (read-only USD/Karma
  preflight), `get_render_stats` (read resolution/samples/renderer/output).
- **`render_layer`:** `create_render_layer` (Solaris RenderProduct or cloned
  Mantra ifd ROP with its own output and object masks), `manage_takes`
  (take lifecycle plus parameter-tuple overrides for render variants).

## Tracer-bullet flow

### Viewport/Render

1. `houdini_camera_light__create_camera(name="rendercam")`
2. `set_render_settings(rop_path="/out/mantra1", camera="/obj/rendercam", resolution=[1280,720], output_path="/tmp/beauty.exr")`
3. `get_render_settings("/out/mantra1")` → verify
4. `capture_viewport(output_path="/tmp/preview.jpg")` for a quick look (UI only; decoded dimensions and pixel extrema are verified, and degenerate frames fail closed)
5. `flipbook(output_path="/tmp/preview.$F4.jpg", frame_range=[1,24,4], camera_path="/obj/rendercam")` for a sparse camera preview (UI only)
6. `render_rop("/out/mantra1", frame_range=[1,1])` → background `job_id` in interactive or headless Houdini

For Mantra, `resolution` enables `override_camerares` and selects the
`res_fraction` user-specified mode; it does not change the camera. Check both
`applied.resolution` and the setter's `readback` before rendering. Missing axes,
missing renderer controls, or writes that do not read back as requested are
reported as `unsupported`, rather than a successful resolution change.
`get_render_settings` and `get_render_stats` follow the active camera, camera
scale, or ROP override. Unresolvable controls and fractional pixel rounding
return explicit `resolution_unresolved` entries. These reads describe the
current parameter context; verify the produced image separately, especially
when a render take, command-line option, or another pipeline overrides it.

For crash-safe final publication, opt in with
`artifact_transaction={"mode":"staged_no_clobber"}` and an explicit integral
frame range. Poll the worker to `completed`, validate each returned staging EXR
externally, then pass the identity-bound receipts to
`finalize_render_outputs(job_id, validator_receipts)`. The worker discovers and
temporarily overrides the exact EXR output parameter only in its loaded HIP
copy. Final paths are created only by the no-clobber finalize step.

### EXR denoising

After the render job completes, call
`denoise_image(input_path="/renders/beauty.001.exr", output_path="/renders/beauty.001.denoised.exr", force_cpu=true)`.
The output directory must already exist and the output file must be new. The
tool resolves `idenoise` only from the adapter host's absolute `HFS/bin`, never
from `PATH` or a caller-provided executable. It performs one image operation
off the scene thread through a Core async job, with a 1–300 second subprocess
timeout; it does not modify the HIP, render settings, or source EXR.

For guides already present in the source, pass `albedo_plane="basecolor"` and
`normal_plane="hitN"`. Omitted guides remain unused. `aovs=["diffuse","indirectDiffuse"]`
selects explicit planes; omitted AOVs use the utility's `C`, `Cf`, `color` defaults.
OIDN is the default; `denoiser="optix"` requires the host's supported NVIDIA
runtime. `force_cpu` applies only to OIDN. No library download, temporal mode,
upscaling, or arbitrary CLI options are exposed.

Inputs are bounded to 512 MiB, 16 megapixels, 8192 pixels per side, and a
64 KiB flat single-part OpenEXR header. Success requires official exit zero,
matching input/output data-window dimensions, unchanged source identity,
and verified output byte hashes after no-clobber publication. The returned
identity receipt distinguishes this from full pixel decoding:
`pixel_decode_verified=false`. Decode the new EXR externally before visual
acceptance, retain the original, and disclose denoising in media provenance.
This is per-image filtering; it does not promise temporal consistency.

Official utility reference: [SideFX idenoise](https://www.sidefx.com/docs/houdini/ref/utils/idenoise.html).

### Render Layers & AOVs

1. For Solaris, `create_render_layer(name="beauty", parent_path="/stage", purpose="beauty", aovs=["diffuse","specular","normal","depth"])`.
2. For Mantra, clone a real pass with an output distinct from its source:
   `create_render_layer(name="solar_fx", parent_path="/out", source_rop_path="/out/mantra1", output_path="/tmp/solar_fx.$F4.exr", candidate_objects="/obj/sun_fx", exclude_objects="/obj/labels", aovs=["emission","depth"])`.
3. `configure_aovs(rop_path="/out/solar_fx", aovs=["normal","depth","normal"], action="add")` adds only missing Mantra planes; `action="remove"` removes matching preset/source/channel planes and compacts the multiparm.
4. `validate_karma_stage(lop_path="/stage/OUT", renderer="karma_xpu")` → inspect instance and RenderVar diagnostics.
5. `get_render_stats(rop_path="/out/solar_fx")` → verify resolution/samples/output.

### Takes

1. `manage_takes(action="create", take_name="lighting_variant_a")`
2. `manage_takes(action="add_override", take_name="lighting_variant_a", node_path="/out/solar_fx", parm_name="vm_picture", value="/tmp/lighting_variant_a.$F4.exr")` → add and set the take-local parameter while restoring the previously current take.
3. `manage_takes(action="remove_override", take_name="lighting_variant_a", node_path="/out/solar_fx", parm_name="vm_picture")` → remove it with the same restoration guarantee.
4. `manage_takes(action="switch", take_name="lighting_variant_a")`
5. `manage_takes(action="list")` → review all takes

Interactive Houdini defaults to an isolated process; poll
`get_render_job(job_id)` and use `cancel_render_job(job_id)` to stop a job
started by the same adapter process. Pass `background=false` only when
foreground execution is intentional. Both interactive and headless Houdini
default to isolated background execution.
Poll and cancel accept the returned 32-character hex job id or its canonical
dashed UUID spelling; both resolve to the same job and process ownership.
The default poll response is bounded: it reports `completed`, `total`,
fractional `progress`, `elapsed_secs`, `eta_secs`, `written_file_count`, and up
to ten `recent_written_files`. `output_verification.state` distinguishes
`verified`, `partial`, `failed`, `not_observed`, and `unavailable` output
evidence. `verified` requires every expected output to be newly written,
readable, non-empty, and produced without an execution/cook failure. Pass
an explicit frame range when exact completeness matters; render and cache jobs
with only part of that requested range written fail with bounded output counts.
Transaction polling additionally returns a bounded transaction state and
aggregate; use `include_details=true` for per-frame staging, validator, commit,
and post-commit verification evidence.
Pass `include_details=true` only when the full
expected-output snapshot, complete written-file and warning lists, error, and
traceback are needed. The same job lifecycle also observes `cache_simulation` and
`execute_rop_chain` jobs.
ROP-chain completion is governed by execution/cook errors; a chain without a
discoverable output pattern can complete with `output_verification.state` set
to `unavailable`. Render and cache jobs still require a new or updated output.
Interactive background launch requires a saved HIP with no unsaved changes and
never auto-saves the GUI scene. Headless background launch requires an existing
HIP and captures its current state in a job-owned temporary HIP snapshot without
saving or renaming the source scene.
The main thread only validates the ROP and launches the isolated process;
Mantra/Karma work never occupies Houdini's event loop. Output-path and
resolution parameter writes are defensive (candidate names) so Mantra, Karma,
and ROP geometry/USD drivers are all tolerated.
