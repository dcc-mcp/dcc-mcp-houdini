---
name: houdini-hda
description: >-
  HDA skill - install, inspect, create, author, publish, validate, cook, and
  synchronize Houdini Digital Assets with typed public parameters. Use when
  loading .hda/.otl assets, building reusable interfaces, or publishing an HDA
  library. Not for generic node edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.19.69+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.1.1"
    tags: [houdini, hda, otl, digital-asset, automation]
    search-hint: "install hda, expose controls, author interface, publish versioned hda, validate contract"
    search-aliases: [use hda, install hda, load otl, run digital asset, instantiate hda, execute hda, save hda, create digital asset, promote hda parameters, author hda interface, publish hda, validate hda, update hda definition, sync hda instance]
    example-prompts:
      - "Install this .hda file and run the asset"
      - "Use the labs::my_asset HDA under /obj with these parameters"
      - "Save /obj/geo1 as a digital asset"
      - "Promote these internal controls and publish a new HDA definition version"
      - "Publish this asset with a safe reusable interface and dependency manifest"
      - "Upgrade this HDA instance and run its version handler"
    intent: "Install, author, publish, validate, instantiate, cook, and synchronize Houdini Digital Assets."
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
2. Use `author_hda_interface` for a complete callback-free declarative interface,
   or `promote_hda_parameters` to clone selected internal parameter tuples.
3. Use `save_node_as_hda` for a new asset, then `publish_hda_library` for an
   explicitly namespaced/versioned library with metadata and dependencies.
4. Gate the result with `validate_hda_contract`.
5. Use `sync_hda_instance` to reload a library, match an instance to the current
   definition, and run its native `SyncNodeVersion` handler.
6. Use `houdini-hda-automation` graph cooking tools when a reusable
   asset needs pipeline-level verification.

`update_hda_definition` updates the current definition. `publish_hda_library`
requires an explicit namespace, version, and overwrite policy.

`save_node_as_hda` refuses an existing target by default. `overwrite=true`
explicitly authorizes Houdini to add or replace definitions in that library
in-place. The write is not atomic; use a new versioned path when an interrupted
write must leave the previous file intact.
