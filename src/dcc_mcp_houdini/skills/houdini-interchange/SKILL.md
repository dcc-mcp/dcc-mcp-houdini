---
name: houdini-interchange
description: >-
  Interchange skill — load-on-demand import/export of Houdini geometry and
  scenes through production formats (native bgeo/geo, OBJ, Alembic, FBX, USD)
  plus filesystem probing. Use these typed tools instead of hand-building
  ROP/LOP/SOP networks with raw scripts.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.33+"
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
  `export_alembic`, `export_fbx`, `export_usd`.

## Format selection guidance

| Goal | Tool | Notes |
|------|------|-------|
| Round-trip Houdini geometry | `export_geometry` → `.bgeo`/`.geo` | Fastest, lossless, native. |
| Hand geometry to another DCC | `export_geometry` → `.obj`, or `export_alembic` | OBJ for static meshes; Alembic for animated/large caches. |
| Animated caches | `export_alembic` with `frame_range` | `render: true` to actually write frames. |
| Rigged/scene to game engine | `export_fbx` | `root_node` selects the `/obj` subtree. |
| USD/Solaris pipelines | `export_usd` | Exports a LOP node's composed `stage()`; reports `root_layer`. |

## Tracer-bullet flow (local, no render farm)

1. `houdini_geometry__create_primitive(parent_path="/obj/geo1", primitive="box")`
2. `export_geometry(node_path="/obj/geo1/box1", output_path="/tmp/box.bgeo")`
3. `probe_file(file_path="/tmp/box.bgeo")` → `exists: true`, `format: geometry`
4. `import_geometry(parent_path="/obj/geo2", file_path="/tmp/box.bgeo")` → round-trip

Export tools that drive a ROP are `async` with generous `timeout_hint_secs`
because caches and FBX writes can be long-running.
