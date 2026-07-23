---
name: houdini-light-rig
description: >-
  Authoring skill — pre-configured lighting templates: three-point rigs,
  HDRI worlds, area softboxes, rig-level intensity controls, and view
  transform management.  Builds on top of houdini-camera-light (individual
  light create/update) to provide higher-level lighting automation.  Pair
  with houdini-camera-light for individual light control and houdini-render
  for render output.
license: MIT
compatibility: "dcc-mcp-houdini 0.4+, Houdini 20.5+, dcc-mcp-core 0.19.69+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [houdini, light-rig, three-point, hdri, area-light, softbox, lighting, lookdev, ocio, view-transform, authoring]
    search-hint: "three point light rig, key fill rim, HDRI dome world, area softbox, lighting template, studio setup, environment light, aim light, group lights, lighting summary, render view transform, OCIO color transform"
    tools: tools.yaml
---

# houdini-light-rig

Typed light-rig authoring tools for agents.  All tools are `affinity: main`.
Complements `houdini-camera-light` (individual light create/update) with
higher-level lighting automation: three-point rigs, HDRI worlds, area
softboxes, rig grouping, and intensity controls.

## Tool groups

- **`light-rig-create`:** `create_three_point_light_rig`, `create_hdri_world`,
  `create_area_softbox`.
- **`light-rig-edit`:** `aim_light_at_object`, `set_light_rig_intensity`,
  `group_lights`, `set_render_view_transform`.
- **`light-rig-query`** (read-only): `get_lighting_summary`, `list_light_rigs`.

## Rig conventions

- A **light rig** is a null node at `/obj` level whose children are `hlight::2.0`
  nodes.  The null name ends with `_rig` by convention.
- `list_light_rigs` scans for nulls matching this pattern; `set_light_rig_intensity`
  and `group_lights` operate on these rig groups.
- Three-point rigs create a null named `<name>` with `_key`, `_fill`, `_rim` lights
  parented underneath.

## Context limitations

- **Karma / Solaris:** This skill operates at `/obj` level with `hlight::2.0`
  nodes.  For USD/Solaris lighting use `houdini-lookdev` and the LOP context.
- **HDRI:** `create_hdri_world` creates an `environment` light with a texture
  map (`envmap` parm).  Ensure the HDRI file path is accessible to the Houdini
  session.
- **View transform:** `set_render_view_transform` configures OCIO-based color
  transforms.  Requires a valid OCIO configuration in the Houdini environment.
- **Aim:** `aim_light_at_object` uses Houdini's built-in `lookatpath` parameter
  — only effective for light types that support look-at (point, spot, area,
  distant).

## Tracer-bullet flow

1. `houdini_camera_light__create_light(light_type="distant", name="key_light")`
2. `create_three_point_light_rig(name="studio_rig", key_intensity=1.2)`
3. `aim_light_at_object(light_path="/obj/studio_rig/studio_rig_key", target_path="/obj/geo1")`
4. `create_hdri_world(hdri_path="/path/to/studio.hdr", intensity=0.8)`
5. `get_lighting_summary()` → review all lights
6. `set_render_view_transform(view_transform="ACES 1.0 SDR-video")`
7. `set_light_rig_intensity(rig_group="/obj/studio_rig", intensity=1.5, multiply=true)`
8. Hand off to `houdini-render` for viewport capture / ROP render
