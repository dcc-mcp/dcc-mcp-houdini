---
name: houdini-copernicus
description: >-
  Typed COP/Copernicus tools for image-processing networks: create a COP
  network, build a bounded filter chain, cook it, verify the output artifact,
  inspect connections, and validate cook errors before handing the result to a
  render or compositing workflow.
license: MIT
compatibility: "dcc-mcp-houdini 0.38+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.1.0"
    tags: [houdini, cop, copernicus, compositing, image, filter, raster, cook, output, validation, terrain, heightfield, fractal, strata]
    search-hint: "cop copernicus image compositing raster blur colorcorrect file filter network cook output artifact terrain heightfield fractal sample strata noise monotoheightfield"
    tools: tools.yaml
---

# houdini-copernicus

Typed Copernicus network authoring and inspection (legacy COP2 is rejected). The skill uses Houdini node types
and parameter readback instead of embedding a large Python recipe, so agents
can compose the same image-processing graph with the existing node and render
skills.

## Copernicus terrain generators (fractal sample + heightfield strata)

Copernicus exposes native heightfield terrain nodes. Two generator families are
first-class aliases so agents do not have to guess raw Houdini node type names:

| Alias | COP node type | Family |
|---|---|---|
| `fractal_sample` | `fractalsample` | fractal sample |
| `fractal_noise` | `fractalnoise` | fractal sample |
| `fractal_noise_3d` | `fractalnoise3d` | fractal sample |
| `strata` / `heightfield_strata` | `heightfield_strata` | heightfield strata |

These node types were confirmed on a live Houdini 22.0.368 Copernicus host. A
procedural terrain chain converts a fractal-noise mono layer into a heightfield
Volume, applies strata, and converts back before a ROP output:
`fractalnoise → mono → monotoheightfield → heightfield_strata → heightfieldtomono → rop_image`.

- `plan_fractal_terrain` returns a deterministic, host-independent plan (node
  types, recommended parameter names, required setup). It does not touch the
  scene, cook, or claim an artifact.
- `create_terrain_generator` creates and wires a single generator node from a
  readable alias. The aliases also work in `create_cop_node` and
  `build_composite_chain` through `resolve_filter_type`.

**Parameter policy:** fractal/strata parameter names vary between Houdini
builds. `RECOMMENDED_PARAMETERS` in the plan are guidance, not auto-applied
defaults. Parameter overrides go through `parameter_edit`: a name the node does
not expose fails the call and rolls back. `plan_fractal_terrain` and
`create_terrain_generator` never cook and never claim a rendered artifact; cook
with `cook_cop_node` and verify with `inspect_cop_output`.

## Supported filter aliases

`file`, `blur`, `colorcorrect`, `ramp`, and `null` use their Copernicus names.
`fractal_sample`, `fractal_noise`, `fractal_noise_3d`, `strata`, and
`heightfield_strata` resolve to the terrain-generator node types above.
`composite` maps to `blend`, and `output` maps to `rop_image`. A raw Houdini node type may also be used when
it matches the namespaced node-type contract. Unsupported or unavailable node types
return a structured error.

## Tracer-bullet flow

1. `create_cop_network(parent_path="/obj/geo1", network_name="copnet1")`
2. `create_cop_node(network_path="/obj/geo1/copnet1", filter_type="file", parameters={...})`
3. `create_cop_node(..., filter_type="blur", input_nodes=["file1"], parameters={...})`
4. `inspect_cop_network(network_path="/obj/geo1/copnet1")`
5. `validate_cop_network(network_path="/obj/geo1/copnet1")`

The response exposes node paths, actual connection endpoints, parameter readback,
and cached cook errors. Missing parameters fail the request; new nodes are removed
on failure. Inputs must belong to the same network. Inspection does not cook, so
validation reports only cached diagnostics. It does not claim a rendered image until a
downstream render skill verifies an output artifact.

## Cooking and output verification

| Tool | Purpose |
|------|---------|
| `build_composite_chain` | Create an ordered chain of filters in one call, each wired into the previous one |
| `cook_cop_node` | Cook a node and report cached errors and warnings, without claiming an artifact |
| `inspect_cop_output` | Resolve the output path and verify whether that file exists on disk |

### Rendering to disk

This package deliberately does **not** ship its own render tool. A Copernicus
output node is a ROP, so `houdini_render__render_rop` already drives it, with
background jobs, cancellation and progress queries:

1. `create_cop_node(network_path=..., filter_type="output")` → `rop_image`
2. `load_skill("houdini-render")` → `houdini_render__render_rop(rop_path=...)`
3. `inspect_cop_output(node_path=...)` → verify the artifact landed on disk

Use `build_composite_chain` when the whole chain is known up front and
`create_cop_node` when iterating step by step. For a validated recipe that
spans node categories, use `houdini_automation__build_node_chain` — this tool
stays Copernicus-specific so it can apply the filter aliases and the Cop
category check.

## Parameter policy

Parameter overrides are applied through `parameter_edit`: a name the node does
not expose **fails the call and rolls back**, so `create_cop_node` and
`build_composite_chain` have no `skipped_parameters` output. A failed chain step
destroys every node the request created.

Legacy COP2 networks remain unsupported and are rejected with a structured
error; Copernicus (`copnet`) is the only supported compositing context.
