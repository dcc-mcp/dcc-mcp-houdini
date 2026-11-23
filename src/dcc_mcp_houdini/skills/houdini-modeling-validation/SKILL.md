---
name: houdini-modeling-validation
description: >-
  Export bounded Houdini SOP modeling state for cross-DCC verification. Use it
  after modeling operations to read back hierarchy, topology counts, UV and
  material evidence, bounds, and explicit unavailable checks.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: validation
    version: "1.0.0"
    tags: [houdini, modeling, validation, model-state, topology, uv, materials]
    search-hint: "Houdini modeling state validation topology UV materials bounds hierarchy model-state"
    search-aliases: [modeling validation, geometry acceptance, mesh readback, cross-DCC modeling]
    tools: tools.yaml
---

# houdini-modeling-validation

Export a bounded `dcc-mcp/model-state@1` payload from one cooked SOP node. The
payload separates observed geometry from unavailable host evidence so the core
verification skill can return `pass`, `fail`, or `unknown` without inferring
success from a cook response.

## Workflow

1. Run a typed operation from `houdini-mesh-ops` or `houdini-geometry`.
2. Call `export_model_state` on the resulting SOP node.
3. Pass the returned `state` to the core `validate_scene_vs_spec` tool.
4. Treat `partial` and `unavailable` as evidence status and retain the payload
   when a check fails.

Houdini SOPs expose geometry facts directly. Object Euler readback and a
portable manifold test are reported as unavailable when the current host does
not provide them through HOM.
