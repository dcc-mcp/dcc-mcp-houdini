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
compatibility: "dcc-mcp-houdini 0.4+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
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
- **`light-rig-shadow`:** `configure_light_shadow` — per-light shadow settings (enable, type, quality, softness, samples, distance, bias, color).
- **`light-rig-filter`:** `configure_light_bank` (categories, selectable, enabled) and `set_light_ies` (IES profile binding).

## Naming: `skipped_parameters` is the only name for "not applied"

Every tool in this adapter reports the things it could **not** apply under one
field name: `skipped_parameters`. Historically three near-synonyms appeared
(`skipped_parameters`, `unapplied_defaults`, `unsupported_settings`); they are
equivalent and have been unified. **Do not introduce another name.**

The field is only legitimate when something is actually reported. A tool whose
parameter overrides go through `parameter_edit` has no skip path at all — the
call fails instead — and must not carry the field.

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
- **HDRI:** `create_hdri_world` creates a native environment light with a texture
  map (`env_map`, or legacy `envmap`). Ensure the HDRI file path is accessible to the Houdini
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
6. `set_render_view_transform(view_transform="ACES 1.0 - SDR Video")`
7. `set_light_rig_intensity(rig_group="/obj/studio_rig", intensity=1.5, multiply=true)`
8. Hand off to `houdini-render` for viewport capture / ROP render

## Shadow configuration

Light types differ in which shadow parameters they expose, so
`configure_light_shadow` resolves each setting against a small alias list and
reports what it could not apply:

- `applied_parameters` — values that were set and read back, keyed by the Houdini
  parameter name that actually matched.
- `skipped_parameters` — settings the light has no parameter for. A caller must
  not read a missing entry as "applied with a default".
- `resolved_names` — which parameter name each setting mapped to.

An unsupported setting name (anything outside the eight supported keys) fails the
call rather than being ignored.

## Light bank and IES profiles

Light bank and IES parameter names differ between Houdini versions and light
types, so both tools resolve each setting against a small alias list rather
than assuming a name:

- `applied_parameters` — values that were set and read back, keyed by the Houdini
  parameter name that actually matched.
- `skipped_parameters` — settings the light has no parameter for. A missing entry
  must not be read as "applied with a default".
- `resolved_names` — which parameter name each setting mapped to.

An unsupported setting name fails the call rather than being ignored.

### `configure_light_bank`

Keys: `categories`, `selectable`, `enabled`. It distinguishes **what the light
had** from **what this call changed it to** — `found_categories` is read before
any write, `applied_categories` is what the light carries afterwards, so a
no-op is not mistaken for a change. When the light exposes none of the aliases,
the call reports `setup_state="unchanged"` and `valid=false`.

### `set_light_ies`

`ies_file` is required; `settings` may add `ies_enabled`, `ies_scale` and
`ies_rotate`. The file is stat-ed **separately** from binding it, following the
same discipline as `inspect_bake_output`:

| `ies_state` | Meaning |
|---|---|
| `resolved` | The path expands and exists on disk |
| `missing` | The parameter was bound, but no file was found at the path |
| `unresolved` | The light exposes no IES parameter, so nothing was bound |

`ies_bound` is true only when the parameter was bound **and** the file exists. A
path that does not resolve is never reported as bound, because a light that
looks configured but renders as if no profile were set is the failure mode this
is here to prevent.

## Honesty contract

- Every tool returns `setup_state` and, where setup remains, `required_setup`.
- No tool reports anything that implies a render was verified: there is no
  `render_verified` field, and a successful configure is not evidence about how
  a frame renders — `required_setup` names that check explicitly.
