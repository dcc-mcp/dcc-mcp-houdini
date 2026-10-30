---
name: houdini-kinefx
description: >-
  Pipeline skill — typed KineFX character animation tools and the end-to-end
  character-animation workflow. Create/configure rig skeletons, biped templates,
  import generated characters, retarget motion, invert rigs, build ragdolls, pack
  APEX FBX bipeds and plan the whole pipeline; also set rig poses, capture skin
  weights, apply mocap and drive Motion Mixer / Full Body IK.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.20.14+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.4.0"
    tags: [houdini, kinefx, rig, skeleton, capture, mocap, retarget, motionclip, motion-mixer, apex, character, animation, pipeline, biped, ragdoll, rig-inversion, fbx, workflow, character-design]
    search-hint: "kinefx rig retarget motion mixer motionclip APEX skeleton pose joint capture mocap character skinning biped ragdoll rig inversion fbx template workflow design codex hyper3d"
    tools: tools.yaml
---

# houdini-kinefx

Typed KineFX character animation tools for agents. Scene tools are
`affinity: main`; the pure planning tools (`plan_character_workflow`,
`design_character`, `biped_joint_map`) are `affinity: any` — they need no Houdini
and are fully unit-testable headless.

KineFX operates at the SOP level — skeletons are geometry with joint point
attributes, rigs are SOP networks, and mocap data is applied via SOP nodes.

The eight-stage character-animation workflow (codex design → hyper3d generation
→ Biped template → biped retarget → rig inversion → Motion Mixer full body IK →
ragdoll → KineFx APEX FBX biped template) is designed in
`docs/guide/houdini-character-animation-workflow.md` and returned as data by
`plan_character_workflow`. External codex/hyper3d steps degrade to offline
equivalents (`design_character`, `import_generated_character`).

## Tool groups

- **`workflow` (pure/headless):** `plan_character_workflow` returns the full
  eight-stage design, gaps/enhancements, external-capability status and
  acceptance criteria; `design_character` emits/validates a structured design
  spec (the codex equivalent); `biped_joint_map` returns cross-convention joint
  maps; `import_generated_character` ingests a generated mesh or builds a proxy
  (the hyper3d equivalent).
- **`rig`:** `create_insect_rig` (anatomy-aware honeybee), `create_rig`
  (generic joint chain), `create_biped_template` (standard 22-joint humanoid
  biped in 5 naming conventions), `invert_rig` (world→local rig inversion).
- **`pose`:** `set_rig_pose` sets joint transforms; `validate_ground_contacts`
  verifies named support joints against one ground surface.
- **`capture`:** `capture_joints` captures skinning weights;
  `deform_gsplat_with_rig` deforms GSplat centers and quaternion orientation.
- **`mocap`:** `apply_mocap` applies FBX/BVH/clip mocap onto a rig skeleton.
- **`retarget/mixer`:** `build_retarget_motion_mixer` builds the Houdini 22 Rig
  Match Pose → Map Points → Full Body IK → MotionClip → APEX → Motion Mixer
  chain (now with optional explicit cross-convention `joint_map`);
  `configure_biped_retarget` builds a single-source retarget with an explicit
  naming map.
- **`simulation`:** `build_ragdoll` builds proxy colliders, a constraint network
  and an RBD solver for a physics ragdoll.
- **`apex`:** `build_apex_fbx_biped` packs an APEX biped character and reports
  the engine-ready FBX export contract.

## Tracer-bullet flow (full character workflow)

1. `plan_character_workflow()` → stages, tools, gaps, external fallbacks.
2. `design_character(style="stylized_game", naming_convention="kinefx")` → spec.
3. `import_generated_character(geo_path="/obj/char", mesh_file="/path/hero.fbx")`
   (or proxy) → rig-ready mesh.
4. `create_biped_template(geo_path="/obj/char", convention="kinefx")` → skeleton.
5. `capture_joints(...)` → skin weights (existing capture skill).
6. `biped_joint_map(source_convention="mixamo", target_convention="kinefx")`.
7. `configure_biped_retarget(...)` and/or `build_retarget_motion_mixer(...)` →
   retarget + Motion Mixer full body IK + APEX character.
8. `invert_rig(...)` → local transforms (rig inversion).
9. `build_ragdoll(...)` → physics ragdoll.
10. `build_apex_fbx_biped(...)` → APEX FBX biped template + `export_fbx` contract.

## Tracer-bullet flow (generic rig)

1. `create_rig(geo_path="/obj/geo1/rig1", joint_chain=[...])` → creates a
   KineFX skeleton inside a Geometry SOP network.
2. `set_rig_pose(rig_node="/obj/geo1/rig1", joint_index=2, translate=[0,1,0])`
3. `validate_ground_contacts(rig_node="/obj/geo1/rig1", ground_node="/obj/ground/OUT", joint_names=["front_L_claw", "middle_R_claw", "rear_L_claw"], min_support_contacts=3)`
4. `capture_joints(geo_path="/obj/geo1", mesh_name="body", rig_name="rig1")`
5. `apply_mocap(geo_path="/obj/geo1", rig_name="rig1", mocap_file="/path/to/walk.fbx")`
