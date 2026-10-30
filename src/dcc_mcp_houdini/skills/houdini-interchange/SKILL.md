---
name: houdini-interchange
description: >-
  Interchange skill — load-on-demand import/export of Houdini geometry and
  scenes through production formats (native bgeo/geo, OBJ, Alembic, FBX, USD)
  plus filesystem probing. Use these typed tools instead of hand-building
  ROP/LOP/SOP networks with raw scripts.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: interchange
    version: "1.0.0"
    tags: [houdini, interchange, import, export, usd, alembic, fbx, obj, bgeo, cache]
    search-hint: "import export usd alembic abc fbx obj bgeo cache save geometry interchange"
    tools: tools.yaml
---

# houdini-interchange

Typed import/export tools for moving geometry and scenes across DCCs. Exports
return structured `written_files`, `skipped`, and `warnings` fields so an agent
can tell what actually landed on disk versus what the installed runtime could
not produce.

## Tool groups

- **`interchange-probe`:** `probe_file` (`affinity: any`, pure filesystem).
- **`interchange-import`:** `import_geometry` (File SOP into a SOP network).
- **`interchange-export`:** `export_geometry` (native/OBJ via `saveToFile`),
  `export_alembic`, `export_fbx`, `export_usd`, `export_sop_to_usd`.

## Format selection guidance

| Goal | Tool | Notes |
|------|------|-------|
| Round-trip Houdini geometry | `export_geometry` → `.bgeo`/`.geo` | Fastest, lossless, native. |
| Hand geometry to another DCC | `export_geometry` → `.obj`, or `export_alembic` | OBJ for static meshes; Alembic for animated/large caches. |
| Animated caches | `export_alembic` with `frame_range` | `render: true` to actually write frames. |
| Rigged/scene to game engine | `export_fbx` | `root_node` selects the `/obj` subtree. |
| USD from a SOP (USD modeling) | `export_sop_to_usd` | Builds a transient SOP Import LOP; reports geometry counts, in-memory composed-stage prim count, and a best-effort disk readback. |
| USD from an existing LOP stage | `export_usd` | Exports a LOP node's composed `stage()`; reports `root_layer`. |

`export_geometry` is the native/OBJ geometry writer. Passing a
`.usd/.usda/.usdc/.usdz` path fails closed with a `next_tools` hint pointing at
`export_sop_to_usd`, so USD outputs go through the typed USD tools. To move SOP
modeling into USD, use `export_sop_to_usd` (SOP → USD) rather than trying to
give `export_usd` a SOP.

`export_fbx` defaults to `convert_units=true`: it enables the native Filmbox
unit-conversion toggle and reports its readback as `unit_conversion_enabled`.
Without conversion, a meter-authored object can arrive 100 times too small
when the FBX declares centimeters. Engines must honor the exported node
transforms and units once; do not add another factor of 100 after conversion.
Use `convert_units=false` only for a pipeline intentionally managing numeric
units itself. An unavailable or mismatched conversion toggle fails before
rendering. Always verify physical world bounds and pivot in the target engine.

## Tracer-bullet flow (local, no render farm)

1. `houdini_geometry__create_primitive(parent_path="/obj/geo1", primitive="box")`
2. `export_geometry(node_path="/obj/geo1/box1", output_path="/tmp/box.bgeo")`
3. `probe_file(file_path="/tmp/box.bgeo")` → `exists: true`, `format: geometry`
4. `import_geometry(parent_path="/obj/geo2", file_path="/tmp/box.bgeo")` → round-trip

## SOP → USD modeling flow

`export_usd` needs a LOP node with `stage()`, which no geometry skill builds.
`export_sop_to_usd` closes that gap with a transient SOP Import LOP:

1. `houdini_geometry__create_primitive(parent_path="/obj/geo1", primitive="box")`
2. (optional) edit with `houdini-mesh-ops` modeling verbs
3. `export_sop_to_usd(node_path="/obj/geo1/box1", output_path="/tmp/box.usd")`
   → `written_files` confirms a fresh file; `source_point_count` /
   `source_primitive_count` and `composed_stage_prim_count` (in-memory) plus
   `disk_prim_count` (best-effort via `Usd.Stage.Open`) report prim counts
4. `probe_file(file_path="/tmp/box.usd")` → `exists: true`, `format: usd`
5. (optional) verify by re-opening the USD; a SOP → USD → SOP File SOP
   round-trip (`import_geometry`) needs native hython validation and is a
   separate acceptance gate.

`Usd.Stage.Export` flattens the composed stage into a single layer; it is not
equivalent to a full USD ROP save. `composed_stage_prim_count` describes the
in-memory stage, not guaranteed on-disk content; `disk_prim_count` is a
best-effort disk readback and is `None` when pxr is unavailable.

Export tools that drive a ROP are `async` with generous `timeout_hint_secs`
because caches and FBX writes can be long-running.
