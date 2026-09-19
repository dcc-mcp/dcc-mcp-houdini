---
name: houdini-terrain
description: >-
  Typed heightfield terrain tools for Houdini. Create a heightfield, add noise,
  erosion, terrace, scatter and other terrain layers, and read back layer names
  and bounds without running a cook.
license: MIT
compatibility: "dcc-mcp-houdini 0.38+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, heightfield, terrain, erosion, noise, scatter, landscape, volume]
    search-hint: "heightfield terrain landscape erode noise terrace scatter slump flowfield mask inspect"
    tools: tools.yaml
---

# houdini-terrain

Typed heightfield authoring for Houdini's native terrain SOPs. Before this
package the adapter had no coverage of Houdini's heightfield toolset, so
terrain work had to go through `execute_python` or generic node creation.

## Tracer-bullet flow

1. `create_heightfield(parent_path="/obj/geo1")`
2. `add_terrain_layer(parent_path="/obj/geo1", layer_type="noise", source_path="/obj/geo1/heightfield1")`
3. `add_terrain_layer(parent_path="/obj/geo1", layer_type="erode", source_path="/obj/geo1/heightfield_noise1")`
4. `add_terrain_layer(parent_path="/obj/geo1", layer_type="scatter", source_path="/obj/geo1/heightfield_erode1")`
5. `inspect_heightfield(node_path="/obj/geo1/heightfield_scatter1")`

Each layer call wires `source_path` into input 0, so chaining is explicit: read
the returned `node_path` and feed it to the next layer.

## Supported layer types

| `layer_type` | SOP |
|---|---|
| `noise` | `heightfield_noise` |
| `erode` | `heightfield_erode` |
| `terrace` | `heightfield_terrace` |
| `distort` | `heightfield_distort` |
| `scatter` | `heightfield_scatter` |
| `slump` | `heightfield_slump` |
| `flowfield` | `heightfield_flowfield` |
| `mask_noise` | `heightfield_masknoise` |
| `copy_layer` | `heightfield_copylayer` |
| `remap` | `heightfield_remap` |

## Parameter policy

The tools create and wire nodes; they do not guess parameter values. SOP
parameters vary between Houdini releases, so an override the node does not
expose **fails the call and rolls back** rather than being silently skipped.
Pass what you want through `parameters` and read `applied_parameters` back.

## Honesty contract

- `create_heightfield` returns `setup_state="skeleton"` and lists the setup a
  renderable terrain still needs, including a `heightfield_output` node.
- `inspect_heightfield` reports `geometry_available=false` instead of guessing
  when the node exposes no cached geometry. Read `layer_names_available` to
  disambiguate: `False` means the read was not available, while an empty list
  with `True` available means the terrain genuinely reports no layers. Never
  infer emptiness from `layer_count=0` alone.
- Creation failures destroy only the nodes owned by the failed request, and
  parameter writes are rolled back (values, expressions and animation).
