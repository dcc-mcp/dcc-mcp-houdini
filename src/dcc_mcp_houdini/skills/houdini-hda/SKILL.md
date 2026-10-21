---
name: houdini-hda
description: >-
  HDA skill - install, inspect, create, author, publish, validate, cook, and
  synchronize Houdini Digital Assets with typed public parameters. Use when
  loading .hda/.otl assets, building reusable interfaces, or publishing an HDA
  library. Not for generic node edits.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 18.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.2.0"
    tags: [houdini, hda, otl, digital-asset, automation]
    search-hint: "install hda, uninstall hda, expose controls, author interface, publish versioned hda, validate contract"
    search-aliases: [use hda, install hda, uninstall hda, load otl, unload otl, run digital asset, instantiate hda, execute hda, save hda, create digital asset, promote hda parameters, author hda interface, publish hda, validate hda, update hda definition, sync hda instance]
    example-prompts:
      - "Install this .hda file and run the asset"
      - "Use the labs::my_asset HDA under /obj with these parameters"
      - "Save /obj/geo1 as a digital asset"
      - "Promote these internal controls and publish a new HDA definition version"
      - "Publish this asset with a safe reusable interface and dependency manifest"
      - "Upgrade this HDA instance and run its version handler"
      - "Uninstall this loaded .hda library from the session"
    intent: "Install, uninstall, author, publish, validate, instantiate, cook, and synchronize Houdini Digital Assets."
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
5. Use `sync_hda_instance` to match an instance to the current definition and run
   its native `SyncNodeVersion` handler. When `hda_file` is provided, that library
   is force-promoted to the current definition first (even if already loaded), and
   the call fails rather than reporting success if the instance does not reach that
   library's version.
6. Use `houdini-hda-automation` graph cooking tools when a reusable
   asset needs pipeline-level verification.
7. Use `uninstall_hda_file` to remove a loaded library from the current session
   when it is no longer needed.

`update_hda_definition` updates the current definition. `publish_hda_library`
requires an explicit namespace, version, and overwrite policy.

`save_node_as_hda` refuses an existing target by default. `overwrite=true`
explicitly authorizes Houdini to add or replace definitions in that library
in-place. The write is not atomic; use a new versioned path when an interrupted
write must leave the previous file intact.

`uninstall_hda_file` is the session-level inverse of `install_hda_file`: it
removes a library's definitions and unregisters its node types for the current
session, but never modifies or deletes the file on disk. Reinstalling the same
file restores the definitions and re-links any existing instances. Uninstalling
a library that is not loaded is a successful no-op. For permanently removing a
single definition from a library file (a disk write), use
`houdini-hda-automation`'s `remove_hda_definition` instead.
