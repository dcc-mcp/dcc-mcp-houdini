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
    version: "1.0.0"
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

When `as_authored` is requested but no material lands in the scene — the carrier
format has no material path in this adapter, or the carrier cannot be decoded —
the import still succeeds for geometry but attaches a warning:

```json
{"code": "material_fallback",
 "message": "material_mode='as_authored' was requested but no materials were imported: this adapter has no material path for 'fbx' carriers",
 "detail": "file=/tmp/showcase.fbx; format=fbx"}
```

Material accounting is always machine-readable in `ImportToSceneResult.extra`:

```json
{"material_mode": "as_authored", "status": "as_authored",
 "materials_detected": 1, "materials_imported": 1,
 "material_paths": ["/mat/asset_brushed_metal"],
 "material_assignments": [{"object": "/obj/asset", "material": "/mat/asset_brushed_metal", "parm": "shop_materialpath"}],
 "unapplied_parameters": []}
```

Check `warnings[].code == "material_fallback"` (or `extra.materials_imported`)
before treating an import as look-complete — a silent `success: true` means the
geometry arrived, not that the look did.

Known limits: only surface PBR values (base colour, metallic, roughness,
emissive, opacity) are translated; textures, UDIM sets and non-PBR shader graphs
are not rebuilt, and a multi-material carrier binds its first material to the
container.

## Gateway flow

```
search_skills("asset import") → load_skill("asset-source") → call("search_assets", {query: "table"})
→ AssetDescriptor → load_skill("houdini-import-to-scene") → call("import_to_scene", {descriptor: ...})
→ ImportToSceneResult
```
