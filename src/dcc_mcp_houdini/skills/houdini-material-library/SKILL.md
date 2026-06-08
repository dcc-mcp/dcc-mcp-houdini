---
name: houdini-material-library
description: >-
  Authoring skill — manage reusable material presets as JSON library files,
  handle texture assignment (image nodes / file paths), reload textures from
  disk, configure OCIO color management and list available color spaces,
  inspect material/shader connections and assignments.  Pair with
  houdini-materials (create/assign) and houdini-lookdev (shader-network
  editing, adapter-owned presets).
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 19.5+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, materials, library, presets, textures, color-management, ocio, shader, assignment, authoring]
    search-hint: "material library, texture management, material preset, color space, OCIO, image reload, shader assignment"
    search-aliases: [save material preset, load material preset, material library, texture assignment, reload texture, color management, ocio config, shader assignment, list color spaces, material connections]
    example-prompts:
      - "Save the clay material as a preset named warm_clay in the library"
      - "List all material presets in the project library"
      - "Assign the brick texture to the basecolor of /mat/wall_shader"
      - "Reload all textures in the scene"
      - "List the available OCIO color spaces"
      - "Which objects is /mat/metal assigned to?"
    intent: "Manage material presets library, textures, color management, and inspect material connections/assignments."
    recall-context:
      app_type: houdini
      domain: lookdev
      workflow-stage: authoring
      task-category: mutate
    requires: []
    produces: [material_preset, texture, image_node, color_space]
    preconditions:
      - type: software
        name: houdini
        version: ">=19.5"
    side-effects:
      creates: true
      modifies: true
      targets: [material, texture, image_node, color_config]
    tools: tools.yaml
---

# houdini-material-library

Typed material-library tools that complement `houdini-materials` (material
create/assign) and `houdini-lookdev` (shader-network editing and adapter-owned
presets).

## Tool groups

- **`library-presets`:** `save_material_preset`, `load_material_preset`,
  `list_material_presets`, `delete_material_preset` — JSON files under a
  user-supplied `library_dir` (defaults to `~/.dcc-mcp/houdini/material_library/`,
  override with `DCC_MCP_HOUDINI_MATERIAL_LIBRARY_DIR`).
- **`library-textures`:** `assign_texture`, `list_images`, `reload_image`.
- **`library-color`:** `set_color_management`, `list_color_spaces` (both
  read Houdini's OCIO configuration).
- **`library-query`** (read-only): `get_material_connections`,
  `get_shader_assignment`.

## Context limitations

- **Presets vs lookdev presets:** This skill operates on a *library directory*
  (`library_dir`) — independent of the `houdini-lookdev` adapter-owned preset
  store.  A library preset captures the full node type and all settable scalar
  parameters; lookdev presets capture evaluated values only.  Choose the
  library path when sharing across projects; choose lookdev presets for
  quick per-user snapshots.
- **Texture mapping:** `assign_texture` creates a file texture VOP
  (`arnold::image` / `mtlximage` / `principledshader` map) or sets a string
  file-path parameter on the target material node.
- **OCIO:** `list_color_spaces` reads from Houdini's active OCIO config;
  `set_color_management` sets the `OCIO` environment variable and triggers a
  Houdini refresh when possible.

## Tracer-bullet flow

1. `houdini_materials__create_material(material_name="brick_wall")`
2. `assign_texture("/mat/brick_wall", "basecolor", "/path/to/brick.exr")`
3. `list_color_spaces()` → discover available options
4. `set_color_management(color_space="ACEScg")`
5. `save_material_preset("/mat/brick_wall", "brick_wall", library_dir="/proj/lib")`
6. `get_shader_assignment(material_path="/mat/brick_wall")` → see which objects use it
