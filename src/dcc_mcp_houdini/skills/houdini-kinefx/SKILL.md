---
name: houdini-kinefx
description: >-
  Pipeline skill — typed KineFX character animation tools. Create and
  configure rig skeletons, set rig poses, capture joint skinning weights,
  and apply motion capture data via SOP-level KineFX nodes.
license: MIT
compatibility: "dcc-mcp-houdini 0.1+, Houdini 20.5+, dcc-mcp-core 0.19.33+"
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: houdini
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [houdini, kinefx, rig, skeleton, capture, mocap, character, animation, pipeline]
    search-hint: "kinefx rig skeleton pose joint capture mocap character skinning bone deform"
    tools: tools.yaml
---

# houdini-kinefx

Typed KineFX character animation tools for agents. All tools are `affinity: main`.

KineFX operates at the SOP level — skeletons are geometry with joint point
attributes, rigs are SOP networks, and mocap data is applied via SOP nodes.

## Tool groups

- **`rig`:** `create_rig` — build a KineFX skeleton rig with a joint chain
  and optional rig pose/attachments.
- **`pose`:** `set_rig_pose` — set the transform of a specific joint or the
  entire rig pose.
- **`capture`:** `capture_joints` — capture skinning weights from joints to
  a target mesh using proximity or bone-capture SOP nodes.
- **`mocap`:** `apply_mocap` — apply motion capture data (FBX, BVH, or
  KineFX clip) onto a rig skeleton.

## Tracer-bullet flow

1. `create_rig(geo_path="/obj/geo1/rig1", joint_chain=[...])` → creates a
   KineFX skeleton inside a Geometry SOP network.
2. `set_rig_pose(rig_node="/obj/geo1/rig1", joint_index=2, translate=[0,1,0])`
3. `capture_joints(geo_path="/obj/geo1", mesh_name="body", rig_name="rig1")`
4. `apply_mocap(geo_path="/obj/geo1", rig_name="rig1", mocap_file="/path/to/walk.fbx")`
