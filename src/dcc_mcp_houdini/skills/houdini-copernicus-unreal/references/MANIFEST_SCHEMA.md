# Copernicus -> Unreal texture-set manifest (schema v1.0)

The sidecar manifest is a deterministic JSON document (sorted keys). It is
written by `export_copernicus_for_unreal` and validated/consumed by
`inspect_unreal_manifest`. No timestamps or host-specific state are embedded,
so identical inputs produce byte-identical output.

## Top-level fields

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Always `"1.0"`. `inspect_unreal_manifest` rejects other versions. |
| `asset_name` | string | Base asset name (identifier), e.g. `Rock_Cliff`. |
| `color_convention` | string | Human-readable statement of the sRGB/linear rule. |
| `destination_path` | string | Unreal Content Browser folder for the textures. |
| `material` | object | `{ name, destination_path }` for the generated material. |
| `textures` | array | One entry per declared map (see below). |
| `import_plan` | array | One `unreal_assets__import_asset` call per texture. |
| `material_plan` | object or null | `unreal_assets__create_texture_material` call, or null if no `base_color`. |
| `warnings` | array | Non-fatal notes (missing artifacts, deferred features). |
| `deferred` | array | Capabilities recorded but not acted upon in v1. |
| `note` | string | Handoff instructions for the Unreal side. |

## `textures[]` entry

| Field | Type | Meaning |
|---|---|---|
| `map_type` | string | One of the canonical PBR slots. |
| `asset_name` | string | Unreal texture asset name (`T_<asset>_<Suffix>`). |
| `object_path` | string | Full `/Game/...` object path for the texture. |
| `source_path` | string | Filesystem path of the rendered source image. |
| `node_path` | string or null | COP output node the source was resolved from. |
| `artifact_exists` | bool | Whether the source file existed at export time. |
| `color_space` | string | `srgb` or `linear`. |
| `srgb` | bool | `true` for color maps. |
| `source_color_space` | string | `srgb` for color maps, `""` for data maps. |
| `non_color_texture` | bool | `true` for data maps. |
| `channel_packing` | string | Descriptive packing (e.g. `rgb`, `r`, `orm`). |
| `udim` | object | `{ enabled, tiles, pattern, deferred }` metadata. |

Color convention is derived from `map_type`: only `base_color` and `emissive`
are sRGB; every other map is linear with `non_color_texture = true`.
`inspect_unreal_manifest` re-derives these values (including
`source_color_space`) and fails if a texture disagrees, so a tampered manifest
cannot silently change color management.

## Fail-closed plan verification

`import_plan` and `material_plan` are not trusted as stored. On inspection the
consumer rebuilds both plans from `textures[]` using the same derivation the
writer used (asset names, `/Game` object paths, color flags and material slots
all derived canonically from `map_type`, `asset_name` and the destination
paths). If the rebuilt plans differ from the stored ones in any value or order,
validation fails. Downgrading a data texture's `non_color_texture` /
`source_color_space`, re-pointing a material slot, or reordering import calls
therefore cannot pass as a "ready-to-use" manifest.

Outside a Houdini session, Houdini variables such as `$HIP` in `source_path`
cannot be expanded; the literal token is recorded, `artifact_exists` is
`false`, and a warning explains the unexpanded token.

## `import_plan[]` entry

```json
{
  "tool": "unreal_assets__import_asset",
  "arguments": {
    "source_path": "/renders/Rock_Cliff_BaseColor.exr",
    "destination_path": "/Game/Textures/Rock_Cliff",
    "asset_name": "T_Rock_Cliff_BaseColor",
    "source_color_space": "srgb",
    "non_color_texture": false
  }
}
```

## `material_plan`

```json
{
  "tool": "unreal_assets__create_texture_material",
  "arguments": {
    "texture_path": "/Game/Textures/Rock_Cliff/T_Rock_Cliff_BaseColor",
    "normal_texture_path": "/Game/Textures/Rock_Cliff/T_Rock_Cliff_Normal",
    "roughness_texture_path": "/Game/Textures/Rock_Cliff/T_Rock_Cliff_Roughness",
    "metallic_texture_path": "/Game/Textures/Rock_Cliff/T_Rock_Cliff_Metallic",
    "ambient_occlusion_texture_path": "/Game/Textures/Rock_Cliff/T_Rock_Cliff_AmbientOcclusion",
    "material_name": "M_Rock_Cliff",
    "destination_path": "/Game/Materials"
  }
}
```

Optional slot arguments are emitted only for declared maps.
`create_texture_material` requires `texture_path`, so the plan is emitted only
when a `base_color` map is present.

## Worked round-trip

```python
# Inside a Houdini session, after rendering COP outputs to disk:
export = houdini_copernicus_unreal__export_copernicus_for_unreal(
    asset_name="Rock_Cliff",
    output_path="$HIP/unreal/Rock_Cliff.manifest.json",
    maps=[
        {"map_type": "base_color", "node_path": "/img/copnet1/basecolor_out"},
        {"map_type": "normal", "source_path": "$HIP/render/Rock_Cliff_Normal.exr"},
        {"map_type": "roughness", "source_path": "$HIP/render/Rock_Cliff_Roughness.exr"},
        {"map_type": "metallic", "source_path": "$HIP/render/Rock_Cliff_Metallic.exr"},
        {"map_type": "ambient_occlusion", "source_path": "$HIP/render/Rock_Cliff_AO.exr"},
    ],
)
# On the Unreal side, feed export["context"]["manifest"] (or the JSON file) to
# unreal_assets__import_asset for each import_plan entry, then call
# unreal_assets__create_texture_material with material_plan["arguments"].
```

`inspect_unreal_manifest(manifest_path)` performs the schema/consumer check on
the Houdini side without a live Unreal session. True end-to-end import (and
Lumen/Nanite/VT behaviour) remains a separate verification gate owned by
quality/release on a real H20.5+/UE5 pair.
