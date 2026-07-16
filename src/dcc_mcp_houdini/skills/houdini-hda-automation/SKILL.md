---
name: houdini-hda-automation
description: >-
  Pipeline skill — HDA library automation and PDG/ROP execution: scan loaded
  HDA libraries, inspect definitions (inputs, parm templates, sections,
  version), instantiate digital assets with inputs/parameters, validate cooked
  nodes, cook TOP/PDG networks, and execute ROP output-driver chains. Pair with
  houdini-hda for install/save and houdini-render for single-ROP captures.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.45+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, hda, otl, digital-asset, pdg, top, rop, render, automation, validation, pipeline]
    search-hint: "hda otl digital asset definition instantiate validate cook pdg top tasks rop output driver render chain dependencies automation"
    tools: tools.yaml
---

# houdini-hda-automation

Typed automation tools for Houdini Digital Assets (HDA/OTL) and procedural
batch execution via PDG/TOP networks and ROP output-driver chains. Complements
`houdini-hda` (which installs/lists/executes/saves HDAs) with library scanning,
definition introspection, instantiation, validation, and graph-level cooking.

## Tool groups

- **`hda-query`** (read-only): `scan_hda_libraries`, `inspect_hda_definition`,
  `validate_hda`.
- **`hda-edit`:** `instantiate_hda` (async — creates and cooks a node).
- **`pdg-rop`** (async): `cook_top_network`, `execute_rop_chain`.

## Context limitations

- **Headless / no license:** all tools degrade through structured
  `skill_error` envelopes when `hou` is unavailable; PDG/ROP cooking still
  requires a valid Houdini session.
- **Long runs:** `instantiate_hda`, `validate_hda`, `cook_top_network`, and
  `execute_rop_chain` are `execution: async` with `timeout_hint_secs` set.
  Interactive `execute_rop_chain` returns an isolated job; poll it through
  `houdini_render__get_render_job` instead of occupying the Houdini event loop.
- **PDG stats:** `cook_top_network` reports `work_item_count` on a best-effort
  basis via `getPDGGraphContext()`; it may be `null` when the context is
  unavailable.
- **ROP dependencies:** `execute_rop_chain` honours upstream ROP inputs by
  default in both foreground and isolated workers; pass `ignore_inputs=true`
  to render only the named driver. Interactive Houdini defaults to isolated
  `hython`, while headless Houdini defaults to foreground. Interactive isolated
  launch requires a saved, clean HIP and never auto-saves the GUI scene.
  Explicit headless isolated launch requires an existing HIP and saves its
  current state before spawning the worker. A chain can complete without a
  discoverable output path when it has no execution/cook errors;
  inspect `output_verification` to distinguish this from verified file output.

## Tracer-bullet flow

1. `scan_hda_libraries()` → find an installed library / node type
2. `inspect_hda_definition("labs::my_asset")` → discover inputs + parm names
3. `instantiate_hda("/obj", "labs::my_asset", parameters={...}, inputs=[...])`
4. `validate_hda("/obj/my_asset1")` → confirm a clean cook
5. `cook_top_network("/obj/topnet1/output")` or
   `execute_rop_chain("/out/mantra1", frame_range=[1, 24])`
