---
name: houdini-geometry
description: >-
  Authoring skill — create common SOP primitives or bounded root-to-tip curve
  guides and inspect SOP geometry: counts, bounds, attributes, groups, and cook
  errors. Use these typed tools to query and seed geometry before custom scripts.
  For mesh edit operations use houdini-mesh-ops.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.91+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.1.0"
    tags: [houdini, geometry, sop, attributes, groups, primitives, curves, guides, grooming, authoring]
    search-hint: "create box sphere grid tube curve, author hair grooming guides root to tip CV cluster, geometry info, point count, attributes, groups, cook errors"
    tools: tools.yaml
---

# houdini-geometry

Typed SOP creation and inspection tools for agents. All tools are `affinity:
main` because they call `hou`. Prefer these over
`houdini-scripting.execute_python` for seeding and querying geometry.

## Tool groups

- **`geometry-create`:** `create_primitive` (box/sphere/grid/tube/curve/null/output)
  and `create_curve_guides` (bounded inline JSON or JSON-file polyline/NURBS
  guide topology).
- **`geometry-query`** (read-only except cook): `get_geometry_info`,
  `list_attributes`, `list_groups`, `get_cook_status`.

## Tracer-bullet flow

1. `create_primitive(parent_path="/obj/geo1", primitive="box")`
2. `get_geometry_info` → counts and bounds
3. edit with `houdini-mesh-ops` (transform/merge/blast/group/normal/convert)
4. `get_cook_status` → verify no cook errors

`get_cook_status` is `async` with a timeout hint because heavy SOP graphs can
cook slowly.

For guide authoring, pass exactly one of `guides` or `input_file`. Each guide
declares root-to-tip `cvs`, `guide_id`, and `cluster_id`; optional per-CV
`widths`/`colors` and `cluster_name` become typed Houdini attributes. The tool
validates the whole bounded payload before creating a Stash SOP and returns the
source SHA-256 (for files), enforced limits, counts, bounds, schema, and any
rejected-guide diagnostics. It never evaluates Python or VEX from the payload.
