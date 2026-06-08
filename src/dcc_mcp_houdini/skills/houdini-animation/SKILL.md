---
name: houdini-animation
description: >-
  Pipeline skill — typed timeline, keyframe, channel, and cache-baking tools.
  Query/set time, FPS and ranges; set/get/delete/list keyframes; inspect
  channels and expressions; export/import channel JSON; bake channels and
  trigger bounded simulation/cache renders. The canonical timeline API.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.18.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, animation, keyframe, channel, timeline, fps, bake, simulation, cache, pipeline]
    search-hint: "keyframe channel timeline frame range fps set time animation bake simulation cache expression"
    tools: tools.yaml
---

# houdini-animation

Typed animation tools for agents. All tools are `affinity: main`.

## Tool groups

- **`timeline`:** `get_timeline`, `set_timeline` — the **canonical** timeline
  query/setter. For interactive timeline edits prefer `set_timeline` over
  `houdini_automation__set_frame_range` (which remains for file-based batch
  flows).
- **`keyframes`:** `set_keyframe`, `get_keyframes`, `delete_keyframes`
  (destructive).
- **`channels`:** `list_animated_parms`, `get_channel_info`, `export_channels`,
  `import_channels` (JSON round-trip).
- **`bake`** (async): `bake_channels` (per-frame sample → constant keys, hard
  frame cap), `cache_simulation` (render a filecache/DOP/geometry ROP, report
  `written_files` + `elapsed_secs`).

## Tracer-bullet flow

1. `set_timeline(frame_range=[1,48], fps=24)`
2. `set_keyframe(node_path="/obj/geo1", parm_name="tx", frame=1, value=0)`
3. `set_keyframe(node_path="/obj/geo1", parm_name="tx", frame=48, value=10)`
4. `get_keyframes("/obj/geo1", "tx")` → verify two keys
5. `export_channels("/obj/geo1", ["tx"], "/tmp/tx.json")` → `import_channels` to retarget
6. `bake_channels("/obj/geo1", ["tx"], frame_range=[1,48])` to flatten expressions

`cache_simulation` is `async` with a 1-hour timeout hint; output-path parm
names are probed defensively so File Cache, DOP I/O, and Geometry ROPs are all
tolerated.
