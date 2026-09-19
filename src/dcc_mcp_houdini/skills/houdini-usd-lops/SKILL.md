---
name: houdini-usd-lops
description: >-
  Solaris/USD skill — read-only inspection of a LOP node's composed Stage plus a
  narrow, typed attribute write path. Use it to list prims, inspect one prim,
  read bounded attribute values, or set attributes on an existing prim. Not for
  USD import, export, prim creation, or variant and layer editing.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: interchange
    version: "1.0.0"
    tags: [houdini, solaris, usd, lops, stage, prims]
    search-hint: "inspect Solaris stage, list USD prims, prim info, read and set USD attributes"
    search-aliases: [inspect usd stage, list lops prims, usd prim info, usd attributes, material binding]
    example-prompts:
      - "List the prims composed by /stage/karma1"
      - "Inspect /World/geo on the Stage from /stage/OUT"
      - "Show bounded attributes containing primvars on /World/geo"
    intent: "Inspect a composed Solaris USD Stage without authoring changes."
    recall-context:
      app_type: houdini
      domain: usd
      workflow-stage: interchange
      task-category: query
    requires: []
    produces: [usd_stage_report]
    preconditions:
      - type: software
        name: houdini
        version: ">=20.5"
    side-effects: {}
    tools: tools.yaml
---

## Naming: `skipped_parameters` is the only name for "not applied"

Writes that the stage refused are reported as `skipped_parameters`, the same
field name every other package uses. Do not introduce a synonym.

# houdini-usd-lops

Read-only inspection of the composed USD Stage returned by a LOP node, plus a
narrow, typed write path for stage attributes.

1. `list_stage_prims` for a bounded Stage inventory.
2. `get_prim_info` for type, state, visibility, transform, bounds, and material binding.
3. `get_prim_attributes` for filtered, size-bounded attribute values at a time code.
4. `set_prim_attributes` for writing a bounded set of attributes and reading them
   back. This is the only tool here that mutates the stage.

```
houdini_usd_lops__set_prim_attributes(
    lop_node_path="/stage/lopnet1",
    prim_path="/hero",
    attributes={"density": 2.5, "center": [1.0, 2.0, 3.0]},
)   # -> applied_attributes, attribute_readback, readback_matches
```

## Write scope

`set_prim_attributes` writes attributes on one existing prim. It does **not**
create or remove prims, edit variants, layers or references, or change the stage
composition graph — those remain outside this package.

Supported value types are bool, int, float, string, float2 and float3; anything
else fails the call rather than being coerced. Two- and three-component values
are converted to `Gf.Vec2f` and `Gf.Vec3f` before the write, because OpenUSD maps
Float2/Float3 onto those types and rejects a raw Python list.

All requested attributes are pre-validated before the first write, so a rejected
entry never leaves a partial write on the stage.

Two failure shapes after that point, both cleaned up rather than left behind:

- **A write the stage refuses** (`Set` returns false): that attribute is
  **removed**, not left holding a default value. An attribute that exists with a
  default reads as "written" to a caller who only checks the name is present.
  Attributes written earlier in the same call are kept.
- **A write that raises**: every attribute this call created is removed.

Either way the names appear in `skipped_parameters` and nowhere else, so the
caller cannot mistake them for applied values. `readback_matches` tells the
caller whether the values read back are the ones written.

Load `houdini-interchange` instead when the task is file import or export.
