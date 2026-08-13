---
name: houdini-kinefx
description: >-
  Pipeline skill — typed KineFX character animation tools. Create and
  configure rig skeletons, set rig poses, capture joint skinning weights,
  and apply motion capture data via SOP-level KineFX nodes.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.70+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.2.0"
    tags: [houdini, kinefx, rig, skeleton, capture, mocap, retarget, motionclip, motion-mixer, apex, character, animation, pipeline]
    search-hint: "kinefx rig retarget motion mixer motionclip APEX skeleton pose joint capture mocap character skinning"
    tools: tools.yaml
---

# houdini-kinefx

Typed KineFX character animation tools for agents. All tools are `affinity: main`.

KineFX operates at the SOP level — skeletons are geometry with joint point
attributes, rigs are SOP networks, and mocap data is applied via SOP nodes.

## Tool groups

- **`rig`:** `create_insect_rig` — build an anatomy-aware worker-honeybee rig
  with six complete leg chains, four wings, flexible abdomen, eyes, antennae,
  and six grounded claw joints; `create_rig` remains the generic joint-chain API
  and optional rig pose/attachments.
- **`pose`:** `set_rig_pose` sets joint transforms;
  `validate_ground_contacts` verifies named support joints against one ground
  surface with numeric clearance and penetration evidence.
- **`capture`:** `capture_joints` captures skinning weights; then
  `deform_gsplat_with_rig` deforms GSplat centers and quaternion orientation
  while preserving anisotropic scale.
- **`mocap`:** `apply_mocap` — apply motion capture data (FBX, BVH, or
  KineFX clip) onto a rig skeleton.
- **`retarget/mixer`:** `build_retarget_motion_mixer` — build the Houdini 22
  Rig Match Pose → Map Points → Full Body IK contract, sample multiple
  MotionClips, pack an APEX character, add named clips, and create a real
  Motion Mixer + Fetch pair with node-level cook validation.

## Tracer-bullet flow

1. `create_rig(geo_path="/obj/geo1/rig1", joint_chain=[...])` → creates a
   KineFX skeleton inside a Geometry SOP network.
2. `set_rig_pose(rig_node="/obj/geo1/rig1", joint_index=2, translate=[0,1,0])`
3. `validate_ground_contacts(rig_node="/obj/geo1/rig1", ground_node="/obj/ground/OUT", joint_names=["front_L_claw", "middle_R_claw", "rear_L_claw"], min_support_contacts=3)`
4. `capture_joints(geo_path="/obj/geo1", mesh_name="body", rig_name="rig1")`
5. `apply_mocap(geo_path="/obj/geo1", rig_name="rig1", mocap_file="/path/to/walk.fbx")`
