---
name: houdini-lookdev
description: >-
  Authoring skill — lookdev and shader-network operations: inspect materials,
  libraries, shader nodes and assignments; get/set shader parameters with
  type-aware validation; inspect and rewire shader connections; reset
  assignments; and manage adapter-owned material presets. Pair with
  houdini-materials for material creation/assignment.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.18.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, lookdev, material, shader, vop, matnet, karma, materialx, preset, authoring]
    search-hint: "material shader lookdev parameter connect disconnect assignment preset save load karma materialx vop"
    tools: tools.yaml
---

# houdini-lookdev

Typed lookdev tools that complement `houdini-materials` (which creates and
assigns materials). Most tools are `affinity: main`; the filesystem-only preset
tools `list_presets` / `delete_preset` are `affinity: any`.

## Tool groups

- **`lookdev-query`** (read-only): `list_materials`, `list_assignments`,
  `get_material_parms`, `get_shader_connections`.
- **`lookdev-edit`:** `set_material_parms`, `connect_shader`,
  `disconnect_shader` (destructive), `reset_material` (destructive).
- **`presets`:** `save_preset`, `list_presets`, `load_preset`, `delete_preset`
  — JSON files under `~/.dcc-mcp/houdini/material_presets/` (override with
  `DCC_MCP_HOUDINI_MATERIAL_PRESET_DIR`).

## Context limitations

- **Karma / MaterialX:** MaterialX subnets live under a `matnet`/`mat` library;
  pass the exact `material_path` (the surface output node). Parameter names
  differ from `principledshader`, so prefer `get_material_parms` to discover
  names before `set_material_parms`.
- **VOP networks:** `connect_shader` / `disconnect_shader` operate on node
  input slots; use `get_shader_connections` to read `inputNames()` first.
- Presets store **evaluated parameter values** only (not node graphs); loading
  onto a different `material_type` is allowed but reported as a warning.

## Tracer-bullet flow

1. `houdini_materials__create_material(material_name="clay")`
2. `get_material_parms("/mat/clay")` → discover parm names
3. `set_material_parms("/mat/clay", {"basecolor": [0.8,0.4,0.2], "rough": 0.6})`
4. `houdini_materials__assign_material("/obj/geo1", "/mat/clay")`
5. `save_preset("/mat/clay", "warm_clay")` → `load_preset` onto another material
