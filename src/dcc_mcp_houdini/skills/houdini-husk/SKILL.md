---
name: houdini-husk
description: >-
  Pipeline skill — command-line USD/Hydra rendering via husk (Karma delegate),
  checkpoint/resume, scene snapshots, and husk option configuration. Pair with
  houdini-karma for renderer setup and houdini-render for viewport/ROP renders.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.69+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, husk, usd, hydra, karma, command_line, checkpoint, snapshot, pipeline]
    search-hint: "husk usd render command line hydra karma checkpoint snapshot resume"
    tools: tools.yaml
---

# houdini-husk

Typed husk command-line rendering tools for USD/Hydra workflows. All tools
are `affinity: main`. `render_with_husk` is `async` with a 1-hour timeout
and falls back to hython in-process rendering when the husk binary is
unavailable.

## Tool groups

- **`render`:** `render_with_husk` — CLI USD rendering via husk with frame
  range, resolution, custom args, and hython fallback.
- **`checkpoint`:** `create_checkpoint` (save intermediate USD state),
  `create_snapshot` (export stage as USD for offline rendering).
- **`options`:** `set_husk_options` — configure or browse husk CLI options
  (renderer, threads, GPU, debug flags) on LOP/ROP nodes.

## Tracer-bullet flow

1. `set_husk_options(list_options=true, category="render")` → browse available options
2. `create_snapshot(source_path="/stage", snapshot_path="/tmp/scene_snapshot.usd", flatten=true)`
3. `set_husk_options(node_path="/stage/karmarenderproduct1", options={"threads": 8, "verbose": true})`
4. `create_checkpoint(usd_file="/tmp/scene_snapshot.usd", checkpoint_path="/tmp/checkpoint_001.usd")`
5. `render_with_husk(usd_file="/tmp/scene_snapshot.usd", output_path="/tmp/render/beauty.$F4.exr", renderer="karma", resolution=[1920, 1080], frame_range=[1, 120])` → `written_files`, `elapsed_secs`

When husk binary is not on PATH, use `use_hython_fallback=true` for in-process
rendering via Houdini's Python session.
