---
name: houdini-import-to-scene
description: >-
  Houdini cross-DCC asset import skill — consumes an AssetDescriptor, imports the
  asset file into a geo container via a File SOP, and returns an
  ImportToSceneResult. Use as the receiving end of the asset import pipeline
  after an asset-source skill resolves the descriptor.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: import
    version: "1.1.0"
    tags: [houdini, asset-import, pipeline, destructive]
    search-hint: >-
      import to scene, asset import, import asset, import fbx, import obj,
      import usd, import abc, import gltf, import glb, cross-dcc import,
      asset descriptor
    search-aliases: [import to scene, asset import, import asset, cross dcc import, import descriptor, houdini import]
    intent: "Import an asset described by an AssetDescriptor into a Houdini geo container and return an ImportToSceneResult."
    recall-context:
      app_type: houdini
      domain: io
      workflow_stage: import
      task_category: import
    preconditions:
      - type: software
        name: houdini
        version: ">=20.5"
    side-effects:
      creates: true
      modifies: true
      imports: true
      targets: [scene_node, geo_container]
    produces: [scene_node, import_result]
    requires:
      - asset-source
    tools: tools.yaml
---

# houdini-import-to-scene

Houdini asset import skill that consumes a validated `AssetDescriptor` from
the shared `dcc_mcp_core.asset_import` contract and imports the asset file into
a Houdini geo container via a File SOP. Returns a typed `ImportToSceneResult`
with imported node names and any non-fatal warnings.

Load this skill after `asset-source` resolves the descriptor.

## Tools

| Tool | Category | Description |
|------|----------|-------------|
| `import_to_scene` | Import | Import an asset from an AssetDescriptor into a Houdini geo container |

## Material handling

A File SOP carries geometry only — Houdini does not rebuild the shading networks
stored in an interchange carrier. `material_mode` therefore has to be honoured
explicitly, and the outcome has to be reported rather than assumed.

| `material_mode` | Behaviour |
|-----------------|-----------|
| `as_authored` (default) | Decode the carrier and rebuild its materials as `principledshader::2.0` nodes under `/mat`, then bind the first one to the geo container through `shop_materialpath`. Supported carriers: glTF/GLB, OBJ+MTL, and USD (via Houdini's bundled `pxr` bindings). |
| `default_gray` | Create and bind one neutral gray material. |
| `skip` | Geometry only; no materials and no warnings. |

The decode outcome is reported in `extra.status`:

| `status` | Meaning | Warning |
|-----------|---------|---------|
| `as_authored` | Every decoded material was created. | no |
| `default_gray` | A neutral gray material was created and bound. | no |
| `no_materials` | The carrier declares no materials (or no USD binding is available to read it). | no — nothing was proven lost |
| `carrier_unreadable` | The carrier declares materials that could not be read (missing `.mtl` sidecar, unknown `usemtl` name, dangling glTF material index, truncated GLB, unopenable USD stage, USD material with no resolvable surface shader, non-`UsdPreviewSurface` shader such as `arnold:standard_surface` or MaterialX). When only *some* materials resolve, the readable ones are still imported and `materials_lost` says how many were dropped. | **yes** |
| `decode_failed` | The carrier could not be decoded at all. | **yes** |
| `unsupported_format` | This adapter has no material path for the format (fbx, abc, bgeo, …). | **yes** |

Only `no_materials` is quiet: a carrier that never had a material loses
nothing. Everything else attaches a `material_fallback` warning naming the
actual cause:

```json
{"code": "material_fallback",
 "message": "material_mode='as_authored' was requested but the authored materials were not imported: the carrier declares materials that could not be read (OBJ declares mtllib asset.mtl but mtllib sidecar(s) not found: asset.mtl)",
 "detail": "file=/data/assets/showcase.obj; format=obj"}
```

A material can also be created with the wrong look: if the shader does not
expose a channel that carries the base look (`base_color`, `metallic`,
`roughness`), the import reports it in `extra.unapplied_required` **and** warns,
rather than reporting a clean `as_authored`. Optional channels (`opacity`,
`emissive`) are only recorded in `extra.unapplied_parameters`.

Material accounting is always machine-readable in `ImportToSceneResult.extra`:

```json
{"material_mode": "as_authored", "status": "as_authored",
 "materials_detected": 1, "materials_imported": 1, "materials_lost": 0,
 "material_paths": ["/mat/asset_brushed_metal"],
 "material_assignments": [{"object": "/obj/asset", "material": "/mat/asset_brushed_metal", "parm": "shop_materialpath"}],
 "unapplied_parameters": [], "unapplied_required": []}
```

`materials_detected` counts what the carrier declares, including materials that
could not be read; `materials_lost` is the part of that count which did not make
it into the scene. A stage with two materials where only one resolves reports
`"materials_detected": 2, "materials_imported": 1, "materials_lost": 1` and
`"status": "carrier_unreadable"`.

Check `warnings[].code == "material_fallback"` (or `extra.materials_imported`)
before treating an import as look-complete — a silent `success: true` means the
geometry arrived, not that the look did.

The asset path is expanded (`~`, environment variables) exactly once, before it
is handed to both the File SOP and the material decoder, so `$ASSETS/x.glb`
cannot reach the geometry import while missing the material decode.

Textured or multi-material glTF/GLB carriers use SideFX's native
`gltf_hierarchy` importer rather than the geometry-only File SOP. Supply
`texture_output_dir` as a new absolute directory for persistent image extraction;
existing directories are refused to prevent replacement of prior textures.
The native importer owns mesh/UV conversion, image extraction, Principled shaders
and primitive material assignments. Its documented parameter contract is checked
at runtime; missing controls fail instead of silently returning to first-material
binding. Only the newly created importer is removed on a build failure. Extracted
files remain available for inspection.

Preflight retains each source mesh/primitive/material index, TEXCOORD_0 accessor,
texture path or embedded-image identity, image SHA-256 and color/data semantics
(base color/emissive sRGB; normal and metallic/roughness raw). Missing local
dependencies, nonlocal URIs, unsupported texture coordinate sets, texture
extensions, required glTF extensions, occlusion and nonopaque modes fail explicitly.
After build, `extra` reports primitive counts per source material, native UV
presence, texture file hashes, enable switches, packed G/B channel selections and
explicit shader color-space menu readback. Any mismatch or unsupported color-space
menu yields `partial_native_materials` plus `material_fallback`, never clean
`as_authored`. Source UV accessor retention and native UV presence are not a
pixel/render or numeric UV-conversion acceptance test.

Native texture/multi-material behavior still needs licensed-host acceptance on
the installed Houdini build. The synthetic GLB/glTF and HOM-double regression
tests establish adapter contracts, not native shader fidelity. The non-glTF
legacy path still translates surface PBR values only; UDIMs/non-PBR graphs and
multi-material OBJ/USD binding remain outside this change.

Native API references: [SideFX glTF object](https://www.sidefx.com/docs/houdini/nodes/obj/gltf_hierarchy.html)
and the official [HDA parameter definitions](https://github.com/sideeffects/HoudiniGLTF/blob/Houdini18.0/src/gltf_hierarchy.hda/Object_1gltf__hierarchy/DialogScript).

## Gateway flow

```
search_skills("asset import") → load_skill("asset-source") → call("search_assets", {query: "table"})
→ AssetDescriptor → load_skill("houdini-import-to-scene") → call("import_to_scene", {descriptor: ...})
→ ImportToSceneResult
```
