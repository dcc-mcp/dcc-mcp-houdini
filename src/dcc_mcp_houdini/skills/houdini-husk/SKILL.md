---
name: houdini-husk
description: >-
  Pipeline skill — command-line USD/Hydra rendering via husk (Karma delegate),
  checkpoint/resume, scene snapshots, and husk option configuration. Pair with
  houdini-karma for renderer setup and houdini-render for viewport/ROP renders.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.91+"
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

Typed husk command-line rendering tools for USD/Hydra workflows. Scene export
and option authoring stay `affinity: main`; native Husk launch, polling, and
cancellation are `affinity: any`. The render process runs below an isolated
hython worker so Karma cannot occupy Houdini's UI thread.

## Tool groups

- **`render`:** `render_with_husk` launches and returns a durable `job_id`;
  `get_husk_job` polls bounded output evidence and `cancel_husk_job` terminates
  only an adapter-owned worker tree.
- **`checkpoint`:** `create_checkpoint` (save intermediate USD state),
  `create_snapshot` (export stage as USD for offline rendering).
- **`options`:** `set_husk_options` — configure or browse husk CLI options
  (renderer, threads, GPU, debug flags) on LOP/ROP nodes.

## Tracer-bullet flow

1. `set_husk_options(list_options=true, category="render")` → browse available options
2. `create_snapshot(source_path="/stage", snapshot_path="/tmp/scene_snapshot.usd", flatten=true)`
3. `set_husk_options(node_path="/stage/karmarenderproduct1", options={"threads": 8, "verbose": true})`
4. `create_checkpoint(usd_file="/tmp/scene_snapshot.usd", checkpoint_path="/tmp/checkpoint_001.usd")`
5. `render_with_husk(usd_file="/tmp/scene_snapshot.usd", output_path="/tmp/render/beauty.$F4.exr", renderer="karma", resolution=[1920, 1080], frame_range=[1, 120])` → `job_id`
6. `get_husk_job(job_id="...")` until `state` is terminal → `written_files`, `elapsed_secs`

`use_hython_fallback=true` is rejected because in-process rendering can freeze
the Houdini event loop. Export a USD snapshot and use the isolated native Husk
path instead.
