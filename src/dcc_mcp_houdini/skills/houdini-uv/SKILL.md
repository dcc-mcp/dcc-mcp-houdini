---
name: houdini-uv
description: >-
  Typed UV tools for Houdini. Create unwrap and transform SOPs and read back UV
  sets and UDIM tiles from cached geometry without running a cook.
license: MIT
compatibility: "dcc-mcp-houdini 0.39+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, uv, unwrap, layout, udim, texture, atlas, transform]
    search-hint: "uv unwrap layout atlas pelt flatten transform fuse udim tile texture inspect"
    tools: tools.yaml
---

# houdini-uv

Typed UV authoring for Houdini's native UV SOPs. Texturing work previously had
to go through `execute_python` or generic node creation; this package covers the
unwrap → pack → inspect loop that texture authoring needs.

## Tracer-bullet flow

1. `unwrap_uv(parent_path="/obj/geo1", unwrap_type="auto", source_path="/obj/geo1/box1")`
2. `transform_uv(parent_path="/obj/geo1", transform_type="layout", source_path="/obj/geo1/uvunwrap1")`
3. `inspect_uv(node_path="/obj/geo1/uvlayout1")` → UV sets and UDIM tiles

Each call returns `node_path`; feed it into the next step's `source_path` to
build the chain.

## Supported node types

| `unwrap_type` | SOP |
|---|---|
| `auto` | `uvunwrap` |
| `atlas` | `uvlayout` |
| `flatten` | `uvflatten` |
| `pelt` | `uvpelt` |
| `quick` | `uvquickshade` |

| `transform_type` | SOP |
|---|---|
| `transform` | `uvtransform` |
| `edit` | `uvedit` |
| `fuse` | `uvfuse` |
| `fit` | `uvfit` |
| `layout` | `uvlayout` |

## UDIM readback

`inspect_uv` reports `udim_tiles` computed as `1001 + floor(u) + 10 * floor(v)`
from the first UV set, sampled with a bounded limit. Read `udim_detection` to
interpret it:

| Value | Meaning |
|---|---|
| `computed` | Tiles were derived from real UV values |
| `no_values` | A UV set exists but its values could not be read |
| `no_uv_sets` | No vertex or point attribute starting with `uv` was found |
| `unavailable` | The node exposed no cached geometry |

## Parameter policy

The tools create and wire nodes; they do not guess parameter values. SOP
parameters vary between Houdini releases, so an override the node does not
expose **fails the call and rolls back** rather than being silently skipped.

## Honesty contract

- `inspect_uv` uses the shared guarded geometry read: a dirty node reports
  `geometry_available=false` instead of being cooked implicitly. Cook first,
  then inspect.
- `unwired` nodes report the setup they still need; the tools never claim a UV
  set exists without reading one.
- Creation failures destroy only the nodes owned by the failed request, and
  parameter writes roll back values, expressions and animation.
