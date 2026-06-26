---
name: houdini-import-to-scene
description: >-
  Houdini cross-DCC asset import skill — consumes an AssetDescriptor, imports the
  asset file into a geo container via a File SOP, and returns an
  ImportToSceneResult. Use as the receiving end of the asset import pipeline
  after an asset-source skill resolves the descriptor.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.18.36+"
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

## Gateway flow

```
search_skills("asset import") → load_skill("asset-source") → call("search_assets", {query: "table"})
→ AssetDescriptor → load_skill("houdini-import-to-scene") → call("import_to_scene", {descriptor: ...})
→ ImportToSceneResult
```
