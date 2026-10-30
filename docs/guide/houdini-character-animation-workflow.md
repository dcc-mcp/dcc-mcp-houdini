# Houdini character-animation workflow — design, gaps and enhancements

This document is the design of record for the eight-stage character-animation
workflow requested in PIP-5119. It covers the full chain:

> codex character design → hyper3d character generation → Biped template →
> biped motion retarget → rig inversion → Motion Mixer full body IK →
> ragdoll → KineFx APEX FBX biped template

The machine-readable form of this design is returned by the
`houdini_kinefx__plan_character_workflow` tool. All implementation lives in the
`houdini-kinefx` bundled skill (plus the existing `houdini-interchange`,
`houdini-simulation`, `houdini-animation` skills it composes).

## 1. Scope and constraints

- The **external** steps (codex, hyper3d) are AI services, not Houdini tools.
  Inside `dcc-mcp-houdini` they are represented by deterministic, offline
  **equivalent alternatives** so the pipeline is fully runnable and testable
  without a live AI service (evidence in §6).
- Every stage maps to a typed tool with an explicit `tools.yaml` contract,
  `affinity`, safety annotations and mock-hou unit tests.
- Node parameters are set with a guarded `_set_if_present` helper and each
  network reports node-level cook failures — matching the existing
  `build_retarget_motion_mixer` convention so the tools degrade gracefully
  across Houdini 20.5/21/22 builds.
- Final visual/cook acceptance on a licensed Houdini host is owned by
  quality/release, not by the implementation (PRE-REVIEW boundary).

## 2. Stage-to-tool map

| # | Stage | Tool(s) | Kind | Input → key output |
|---|-------|---------|------|--------------------|
| 1 | Character design (codex) | `design_character` | equivalent (pure) | prompt/style → validated design spec JSON |
| 2 | Character generation (hyper3d) | `import_generated_character` (+ `houdini_import_to_scene__import_to_scene`) | equivalent | generated `AssetDescriptor`/FBX/OBJ/ABC → rig-ready mesh SOP or proxy |
| 3 | Biped template | `create_biped_template` | new | spec → 22-joint humanoid KineFX skeleton |
| 4 | Biped motion retarget | `biped_joint_map`, `configure_biped_retarget`, `build_retarget_motion_mixer` | new + enhanced | source + target → retargeted animated skeleton |
| 5 | Rig inversion | `invert_rig` (+ `_character_common.compute_local_transforms`) | new | world-posed skeleton → parent-relative local transforms |
| 6 | Motion Mixer full body IK | `build_retarget_motion_mixer` (enhanced) | enhanced | 2+ clips → APEX character + Motion Mixer/Fetch |
| 7 | Ragdoll | `build_ragdoll` (+ `houdini_simulation__create_constraint_network`) | new | biped skeleton → DOP RBD ragdoll setup |
| 8 | KineFx APEX FBX biped template | `build_apex_fbx_biped` (+ `houdini_interchange__export_fbx`) | new | biped skeleton/mesh → APEX character + FBX export |

### Data flow

```
design_character ──> design_spec ───────────────┐
                                                v
import_generated_character (or proxy) ──> mesh SOP ──> capture_joints (existing)
                                                            │
create_biped_template ──> biped skeleton ───────────────────┤
        │                                                   v
        │  biped_joint_map (source/target conventions)      skinned character
        v                                                   │
configure_biped_retarget / build_retarget_motion_mixer <───────┤
        │  (Rig Match Pose → Map Points → Full Body IK)      │
        v                                                   │
invert_rig (world→local transforms)                         │
        │                                                   │
        ├──> build_ragdoll (RBD proxy + constraints)        │
        │                                                   │
        └──> build_apex_fbx_biped ──> export_fbx contract <──┘
```

## 3. Gap / enhancement list

| ID | Kind | Stage | Gap or problem | Resolution |
|----|------|-------|----------------|------------|
| G1 | gap | 1 | No in-Houdini character-design contract; codex output free-form | `design_character` emits/validates a strict design spec |
| G2 | gap | 2 | No tool ingests a hyper3d/Rodin generated mesh | `import_generated_character` imports/normalizes or builds a proxy |
| G3 | gap | 3 | `create_rig` generic / `create_insect_rig` honeybee; no humanoid biped | `create_biped_template` (22 joints, 5 conventions) |
| G4 | gap | 4 | Retarget assumed identical joint names (auto map) | `biped_joint_map` + `configure_biped_retarget` explicit cross-convention map |
| G5 | gap | 5 | No rig-inversion capability | `invert_rig` world→local transform inversion (pure math + scene mode) |
| G6 | gap | 7 | Only generic RBD blocks; no character ragdoll | `build_ragdoll` proxy colliders + constraint net + solver |
| G7 | gap | 8 | No APEX FBX biped template / export path | `build_apex_fbx_biped` packs APEX + reports `export_fbx` |
| E1 | enhancement | 6 | `build_retarget_motion_mixer` auto-maps identical names only | optional `joint_map` / `source_convention`+`target_convention` switch to explicit mapping (backward compatible) |
| E2 | enhancement | 4 | No shared naming/linear-algebra layer | `_character_common` centralizes conventions + FK-inversion math |

## 4. Key contracts

### Character design spec (`design_character`)

`dcc-mcp-houdini.character-design/v1` — `name`, `style` (realistic/stylized/
cartoon/stylized_game), `engine`, `target_height`, `naming_convention`,
`up_axis`, `face_forward`, `skeleton`, `features`, `pipeline`. An external LLM
(codex) can author the same JSON; the tool validates required fields and
conventions. This is what makes the "codex design" step reproducible offline.

### Biped naming map (`biped_joint_map`)

22 canonical joints (`hips`, `spine`…, `head`, `clavicle_l/r`, `upperarm_l/r`,
`lowerarm_l/r`, `hand_l/r`, `thigh_l/r`, `calf_l/r`, `foot_l/r`, `toe_l/r`)
mapped across `kinefx`, `biped` (3ds Max Biped), `mixamo`, `unreal`
(Mannequin) and `fbx`. Returned as `source_name → target_name` pairs used to
author the `retarget_joint` point attribute consumed by `kinefx::mappoints` and
`kinefx::fullbodyik`.

### Rig inversion (`invert_rig`)

Pure FK inverse: `local[i] = inverse(world[parent[i]]) · world[i]` (world for
roots). Verifiable with 4×4 matrix unit tests with no Houdini. Scene mode reads
a KineFX skeleton's `transform`/`P` point attributes and writes local
transforms to a fresh skeleton SOP's stash.

## 5. Tracer-bullet flow

```
plan_character_workflow()
design_character(style="stylized_game", naming_convention="kinefx")
import_generated_character(geo_path="/obj/char", mesh_file="/path/hero.fbx")
create_biped_template(geo_path="/obj/char", convention="kinefx", height=1.7)
capture_joints(...)                      # existing capture skill
biped_joint_map("mixamo", "kinefx")
configure_biped_retarget(geo_path="/obj/char", target_skeleton=..., source_skeleton=...,
                         source_convention="mixamo", target_convention="kinefx")
build_retarget_motion_mixer(geo_path="/obj/char", ...)   # stage 6, enhanced
invert_rig(rig_node="/obj/char/biped")                   # stage 5
build_ragdoll(geo_path="/obj/char", skeleton="/obj/char/biped")
build_apex_fbx_biped(geo_path="/obj/char", skeleton="/obj/char/biped",
                     output_fbx="/out/biped.fbx")
houdini_interchange__export_fbx(...)     # per returned contract
```

## 6. External capability evidence and equivalent alternatives

Recorded against this runtime (see the Monica issue comment for the raw probe
output). Facts:

- **codex**: a generic Codex/LLM coding agent CLI is present (`codex-cli`, logged
  in), but it is **not a Houdini MCP tool** and has no character-design endpoint
  bound to this adapter. Free-form LLM output cannot be consumed directly by the
  pipeline.
- **hyper3d**: an `HYPER3D_API_KEY` environment value is present and a
  host-neutral `dcc-ai-hyper3d` skill package exists locally (its
  `create_rodin_task` / `download_assets` tools generate a mesh and return an
  `AssetDescriptor` with a `local_path` and `format`). However it is **not
  registered as a running MCP server** in this adapter's config, and cloud
  generation needs network + credentials — so it is an **out-of-band** step that
  cannot be invoked from within a Houdini skill call. Its `AssetDescriptor` is
  already the input contract of the existing
  `houdini_import_to_scene__import_to_scene` tool.

Equivalent alternatives (offline, deterministic):

| External step | Equivalent | What it does |
|---------------|-----------|--------------|
| codex character design | `design_character` | deterministic, validated design spec; any LLM (incl. codex) can author the same JSON schema |
| hyper3d character generation | `import_generated_character` (+ `houdini_import_to_scene__import_to_scene`) | ingests a hyper3d `AssetDescriptor.local_path` or any generated FBX/OBJ/ABC/bgeo/USD mesh, normalizes units/height, or builds a procedural proxy when offline |

This keeps every downstream stage runnable and testable without the external
services; when those services are available, their `AssetDescriptor`/file
outputs feed the same import and validation tools. Note the hyper3d skill's own
guidance: OBJ outputs may lack auto-bound textures and FBX/GLB carry unit
conversion — verify geometry, UVs, material bindings and scene scale after
import (owned by QA on a licensed host).

## 7. Acceptance criteria

- All eight stages have a typed tool or a documented equivalent alternative.
- External steps degrade to offline equivalents with recorded evidence.
- Biped joint names are stable and map across 5 naming conventions.
- Retarget supports explicit cross-convention joint maps (not only auto map).
- Rig inversion is verifiable with pure linear-algebra unit tests (no Houdini).
- Every tool has mock-hou unit tests, a `tools.yaml` contract and passes skill lint.
- Final visual/cook acceptance on a licensed Houdini 20.5+/22 is owned by QA/release.

## 8. Reproduce / verify

```sh
vx just lint-skills        # SKILL.md + tools.yaml contract
vx just check-py37-syntax  # Python 3.7 grammar gate (red line)
vx just test               # includes the mock-hou workflow tests
```

Scene-node cook and FBX round-trip verification on licensed Houdini is a
separate QA step (see `docs/ci/houdini-docker.md` and the FBX acceptance
script `.github/scripts/run_houdini_fbx_units_acceptance.py`).
