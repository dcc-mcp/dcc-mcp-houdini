---
name: houdini-copernicus-unreal
description: >-
  Interchange skill - build a deterministic Copernicus-to-Unreal PBR texture-set
  sidecar manifest from COP output nodes or source files, with fixed color-space
  and /Game naming conventions plus ready-to-call Unreal import/material plans.
  Use when handing Houdini Copernicus textures to Unreal Engine. Not for
  rendering/cooking COP networks, USD/Asset Sync publishing, FBX/HDA export, or
  live Houdini-Engine/SessionSync links.
license: MIT
compatibility: "dcc-mcp-houdini 0.45+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: interchange
    version: "1.0.0"
    tags: [houdini, copernicus, cop, unreal, texture, pbr, export, interchange, manifest]
    search-hint: "copernicus unreal pbr texture export import_asset create_texture_material srgb linear /Game manifest"
    tools: tools.yaml
---

# houdini-copernicus-unreal

Offline, single-repo bridge from Houdini Copernicus (COP) image outputs to an
Unreal Engine PBR material. It produces a **deterministic, named texture set**
as a sidecar JSON manifest, together with ready-to-call `dcc-mcp-unreal`
`import_asset` and `create_texture_material` plans.

This skill does **not** render or cook. Produce the COP outputs first with
`houdini_render__render_rop` and verify them with
`houdini_copernicus__inspect_cop_output`; then declare the maps here.

## Color convention (fixed)

| map_type | color_space | source_color_space | non_color_texture | create_texture_material slot |
|---|---|---|---|---|
| `base_color` | srgb | `srgb` | false | `texture_path` |
| `normal` | linear | `""` | true | `normal_texture_path` |
| `roughness` | linear | `""` | true | `roughness_texture_path` |
| `metallic` | linear | `""` | true | `metallic_texture_path` |
| `ambient_occlusion` | linear | `""` | true | `ambient_occlusion_texture_path` |
| `emissive` | srgb | `srgb` | false | (imported only) |
| `opacity`, `height`, `displacement`, `specular` | linear | `""` | true | (imported only) |

These values map 1:1 onto `unreal_assets__import_asset`
(`source_color_space`, `non_color_texture`) and
`unreal_assets__create_texture_material` arguments, so the Unreal side consumes
the manifest without re-deriving color management.

## Flow

1. `export_copernicus_for_unreal(maps, asset_name, output_path, ...)` — each
   `maps` item carries a `map_type` plus either `node_path` (a COP output node,
   probed via `hou` for its output file) or `source_path` (an explicit file).
   Optional `channel_packing` and `udim` descriptors are recorded as metadata.
2. It writes `<output_path>` — a deterministic manifest containing:
   - `textures[]` with map type, Unreal asset name, `/Game` object path, source
     file, color space, sRGB / non-color flags, channel packing and UDIM metadata;
   - `import_plan[]` — one `unreal_assets__import_asset` call per texture;
   - `material_plan` — one `unreal_assets__create_texture_material` call
     (present only when a `base_color` map is declared);
   - `warnings`, `deferred` capability notes, and a `note` describing the handoff.
   Artifact presence is reported in the tool result (`artifacts_present`); the
   manifest records `artifact_exists` per texture but never claims a render.
   Outside a Houdini session a `$HIP`/`$F` token in `source_path` is recorded
   literally (it cannot be expanded), so `artifact_exists` is `false` and a
   warning explains the unexpanded token.
3. `inspect_unreal_manifest(manifest_path)` — validates the schema, re-derives
   the color convention for every texture, and rebuilds `import_plan` and
   `material_plan` from `textures[]`, failing closed if the stored plans were
   tampered with. It then returns those ready-to-use plans and the texture list,
   proving the manifest is consumable without a live Unreal session.

See `references/MANIFEST_SCHEMA.md` for the exact JSON schema and a worked
round-trip example.

## Scope and defaults

- Default `destination_path`: `/Game/Textures/<asset_name>`; material:
  `M_<asset_name>` in `/Game/Materials`; texture assets:
  `T_<asset_name>_<Suffix>` (e.g. `T_Rock_Cliff_BaseColor`).
- A `base_color` map is required to emit `material_plan`; otherwise a warning
  is recorded and `material_plan` is `null`.
- `map_type` values must be unique; unknown types are rejected (fail closed).
- `channel_packing` is descriptive metadata. ORM packing, UDIM / virtual
  texturing, OCIO/ACES color configuration, Lumen/Nanite, and live
  Houdini-Engine/SessionSync links are **out of scope for v1** and recorded
  under `deferred` only — the skill never acts on them.
- Python 3.7 compatible; no `hou` import at module load (lazy, inside the tool
  when a `node_path` is used). The skill writes exactly one file — the manifest
  at the caller-supplied `output_path` — and reads source artifacts only; it
  does not scan or modify any other directory. `output_path` is caller-chosen
  (any writable path), so it is not sandboxed and should be set deliberately.
  This keeps the py37 CI syntax gate green and needs no Unreal-side changes.
