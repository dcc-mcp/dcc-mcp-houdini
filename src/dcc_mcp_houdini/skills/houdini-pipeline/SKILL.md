---
name: houdini-pipeline
description: >-
  Pipeline skill — generic, adapter-owned project and shot/package automation:
  set/query the project root, tag and read portable asset metadata, validate a
  scene for missing files / bad output dirs / dirty state / cook errors,
  collect file dependencies into a manifest (no copying), and export a
  shot/package manifest (frame range, cameras, output nodes, caches, written
  files). No dependency on private production services.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.45+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, pipeline, project, job, metadata, validation, dependencies, shot, package, manifest, export]
    search-hint: "project job workspace root asset metadata tag validate scene missing files dependencies manifest collect shot package export frame range cameras caches outputs"
    tools: tools.yaml
---

# houdini-pipeline

Generic, public pipeline helpers that stay **adapter-owned** and
**filesystem-oriented**. They deliberately avoid any dependency on private
production services — external integrations are left as optional extension
points (consume the returned manifests in your own publish step).

## Tool groups

- **`project`:** `set_project`, `get_project` — manage `$JOB` with explicit
  paths and structured validation.
- **`metadata`:** `tag_asset_metadata`, `get_asset_metadata` — store/read a
  portable JSON payload under the `dcc_mcp_meta:` user-data key on a node or
  the hip file.
- **`validation`** (read-only): `validate_scene`, `collect_dependencies` —
  surface missing files, bad output dirs, dirty state, cook errors, and a
  dependency manifest (never copies files).
- **`package`:** `export_shot_package` — manifest of frame range, fps,
  cameras, output nodes, caches, and written files; optional JSON write.

## Context limitations

- **No private services:** metadata uses a generic, adapter-owned schema; the
  shot manifest is plain JSON you can feed into any downstream pipeline.
- **No implicit copying:** `collect_dependencies` and `export_shot_package`
  return manifests only; `export_shot_package` writes a file solely when
  `write_manifest=true` and an `output_path` is given.
- **Heuristic file-parm detection:** file references are detected via string
  parm templates with a `FileReference` string type, with name-based heuristics
  (`output` / `sopoutput` / `picture` / `lopoutput`) to classify outputs.
- **Headless friendly:** all tools degrade through structured `skill_error`
  envelopes when `hou` is unavailable.

## Tracer-bullet flow

1. `set_project("/projects/showA/shot010", create=true)`
2. `tag_asset_metadata({"shot": "sh010", "artist": "me"}, node_path="/obj")`
3. `validate_scene()` → fix any `missing_files` / `bad_output_dirs`
4. `collect_dependencies()` → review the dependency manifest
5. `export_shot_package(output_path="/projects/showA/shot010/package.json", write_manifest=true)`
