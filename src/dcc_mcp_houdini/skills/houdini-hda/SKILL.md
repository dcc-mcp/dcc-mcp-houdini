---
name: houdini-hda
description: >-
  HDA skill - install, inspect, create, cook, publish, version, and synchronize
  Houdini Digital Assets with typed public parameters. Use when loading .hda/.otl
  assets, turning a node graph into a reusable HDA, or upgrading an HDA instance.
  Not for generic node edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.19.45+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.1.0"
    tags: [houdini, hda, otl, digital-asset, automation]
    search-hint: "install hda, expose controls, publish definition, upgrade instance, save digital asset"
    search-aliases: [use hda, install hda, load otl, run digital asset, instantiate hda, execute hda, save hda, create digital asset, promote hda parameters, update hda definition, sync hda instance]
    example-prompts:
      - "Install this .hda file and run the asset"
      - "Use the labs::my_asset HDA under /obj with these parameters"
      - "Save /obj/geo1 as a digital asset"
      - "Promote these internal controls and publish a new HDA definition version"
      - "Upgrade this HDA instance and run its version handler"
    intent: "Install, inspect, instantiate, cook, publish, version, and synchronize Houdini Digital Assets."
    recall-context:
      app_type: houdini
      domain: assets
      workflow-stage: authoring
      task-category: mutate
    requires: []
    produces: [scene_node, file:hda]
    preconditions:
      - type: software
        name: houdini
        version: ">=18.5"
    side-effects:
      creates: true
      modifies: true
      file-output: true
      targets: [scene_node, file:hda]
    tools: tools.yaml
---

# houdini-hda

Typed Houdini Digital Asset operations. `execute_hda` is the main high-level
entry point: it can install an asset file, instantiate a node, set parameters,
press button parms, and cook the node.

## Reusable asset lifecycle

1. Build and test the internal node graph.
2. Use `promote_hda_parameters` on an unlocked HDA or subnet to clone selected
   parameter tuples onto its public interface and link the internal controls.
3. Use `save_node_as_hda` for a new asset, or `update_hda_definition` to publish
   unlocked edits and advance an existing definition version.
4. Use `sync_hda_instance` to reload a library, match an instance to the current
   definition, and run its native `SyncNodeVersion` handler.
5. Use `houdini-hda-automation` inspection and validation tools when a reusable
   asset needs pipeline-level verification.

`update_hda_definition` updates the current definition. Creating or migrating
between separately namespaced operator types remains an explicit pipeline choice.
