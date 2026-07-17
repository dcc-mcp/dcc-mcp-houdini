# Houdini Bundled Skills Index

Progressive loading stages for `dcc-mcp-houdini`. Minimal mode loads **bootstrap + scene** at startup.

| Stage | Skills | Default loaded |
|-------|--------|----------------|
| `bootstrap` | `houdini-scripting` | yes |
| `scene` | `houdini-scene`, `houdini-scene-edit` | `houdini-scene` only |
| `authoring` | `houdini-nodes`, `houdini-object-ops`, `houdini-parameters`, `houdini-node-graph`, `houdini-geometry`, `houdini-mesh-ops`, `houdini-camera-light`, `houdini-materials`, `houdini-lookdev`, `houdini-material-library`, `houdini-hda`, `houdini-light-rig` | no |
| `interchange` | `houdini-interchange`, `houdini-export-preset`, `houdini-import-to-scene`, `houdini-usd-lops` | no |
| `pipeline` | `houdini-render`, `houdini-karma`, `houdini-husk`, `houdini-animation`, `houdini-chops`, `houdini-constraints`, `houdini-kinefx`, `houdini-hda-automation`, `houdini-pipeline`, `houdini-dev`, `houdini-automation`, `houdini-texture-bake` | no |

## Common chains

| Task | Chain |
|------|-------|
| Verify MCP session | `houdini_scripting__get_session_info` |
| Inspect hip | `houdini_scene__get_scene_info` → `houdini_scene__list_obj_nodes` |
| Scene lifecycle | `load_skill("houdini-scene-edit")` → `houdini_scene_edit__open_scene` / `houdini_scene_edit__save_scene` |
| Select & frame | `load_skill("houdini-scene-edit")` → `houdini_scene_edit__find_nodes` → `houdini_scene_edit__set_selection` → `houdini_scene_edit__get_bounding_box` |
| Edit existing object | `load_skill("houdini-object-ops")` → `houdini_object_ops__get_transform` → `houdini_object_ops__set_transform` → `houdini_object_ops__set_node_flags` |
| Build SOP/OBJ network | `load_skill("houdini-nodes")` → `houdini_nodes__create_node` → `houdini_nodes__set_node_parms` → `houdini_nodes__connect_nodes` → `houdini_nodes__cook_node` |
| Edit parameters & expressions | `load_skill("houdini-parameters")` → `houdini_parameters__list_parms` → `houdini_parameters__set_parms` / `houdini_parameters__set_expression` |
| Inspect & rewire graph | `load_skill("houdini-node-graph")` → `houdini_node_graph__get_connections` → `houdini_node_graph__connect_input` / `houdini_node_graph__disconnect_input` |
| Create & inspect geometry | `load_skill("houdini-geometry")` → `houdini_geometry__create_primitive` → `houdini_geometry__get_geometry_info` → `houdini_geometry__list_attributes` / `houdini_geometry__list_groups` |
| Edit a mesh procedurally | `load_skill("houdini-mesh-ops")` → `houdini_mesh_ops__transform_geometry` / `merge_geometry` / `blast_geometry` / `group_geometry` / `add_normals` / `triangulate_geometry` / `convert_geometry` → `houdini_geometry__get_cook_status` |
| Set up cameras & lights | `load_skill("houdini-camera-light")` → `houdini_camera_light__create_camera` → `houdini_camera_light__create_light` → `houdini_camera_light__frame_view` |
| Three-point studio lighting | `load_skill("houdini-light-rig")` → `create_three_point_light_rig` → `aim_light_at_object` → `set_light_rig_intensity` → `get_lighting_summary` |
| HDRI environment lighting | `load_skill("houdini-light-rig")` → `create_hdri_world` → `area_softbox` / `set_render_view_transform` → `get_lighting_summary` |
| Light rig management | `load_skill("houdini-light-rig")` → `list_light_rigs` → `group_lights` → `set_light_rig_intensity` |
| Render & verify | `load_skill("houdini-render")` → `houdini_render__set_render_settings` → `houdini_render__capture_viewport` → `houdini_render__render_rop` → `houdini_render__get_render_job` / `houdini_render__cancel_render_job` |
| Karma stage preflight | `load_skill("houdini-render")` → `houdini_render__validate_karma_stage(lop_path="/stage/OUT", renderer="karma_xpu")` |
| Texture bake (AO) | `load_skill("houdini-texture-bake")` → `houdini_texture_bake__list_bake_targets` → `houdini_texture_bake__bake_ambient_occlusion` |
| Texture bake (lighting) | `load_skill("houdini-texture-bake")` → `houdini_texture_bake__list_bake_targets` → `houdini_texture_bake__bake_lighting` |
| Transfer high→low maps | `load_skill("houdini-texture-bake")` → `houdini_texture_bake__list_bake_targets` → `houdini_texture_bake__transfer_maps` |
| Create and assign material | `load_skill("houdini-materials")` → `houdini_materials__create_material` → `houdini_materials__assign_material` |
| Animate & bake | `load_skill("houdini-animation")` → `houdini_animation__set_timeline` → `houdini_animation__set_keyframe` → `houdini_animation__get_keyframes` → `houdini_animation__bake_channels` / `houdini_animation__cache_simulation` |
| Validate an animation loop | `load_skill("houdini-animation")` → `houdini_animation__validate_loop_contract` (unique playback samples; periodic seam uses virtual `end+step`) |
| Lookdev & shader networks | `load_skill("houdini-lookdev")` → `houdini_lookdev__list_materials` → `houdini_lookdev__get_material_parms` → `houdini_lookdev__set_material_parms` → `houdini_lookdev__save_preset` / `houdini_lookdev__load_preset` |
| Material library & presets | `load_skill("houdini-material-library")` → `houdini_material_library__list_material_presets` → `houdini_material_library__save_material_preset` / `houdini_material_library__load_material_preset` → `houdini_material_library__assign_texture` |
| Inspect textures & colors | `load_skill("houdini-material-library")` → `houdini_material_library__list_images` → `houdini_material_library__list_color_spaces` → `houdini_material_library__reload_image` |
| Run an HDA | `load_skill("houdini-hda")` → `houdini_hda__execute_hda` |
| Publish or revise an HDA | `load_skill("houdini-hda")` → `houdini_hda__author_hda_interface` → `houdini_hda__save_node_as_hda` / `houdini_hda__publish_hda_library` → `houdini_hda__validate_hda_contract` → `houdini_hda__sync_hda_instance` |
| Cross-DCC asset import | `load_skill("houdini-import-to-scene")` → `houdini_import_to_scene__import_to_scene` (uses AssetDescriptor contract from dcc-mcp-core) |
| Probe / import / export files | `load_skill("houdini-interchange")` → `houdini_interchange__probe_file` → `houdini_interchange__import_geometry` / `houdini_interchange__export_geometry` / `export_alembic` / `export_fbx` / `export_usd` |
| Inspect a Solaris USD Stage | `load_skill("houdini-usd-lops")` → `houdini_usd_lops__list_stage_prims` → `houdini_usd_lops__get_prim_info` / `houdini_usd_lops__get_prim_attributes` |
| Manage export presets | `load_skill("houdini-export-preset")` → `houdini_export_preset__save_export_preset` → `houdini_export_preset__list_export_presets` → `houdini_export_preset__load_export_preset` |
| Automate HDA + PDG/ROP | `load_skill("houdini-hda-automation")` → `houdini_hda_automation__scan_hda_libraries` → `houdini_hda_automation__inspect_hda_definition` → `houdini_hda_automation__instantiate_hda` → `houdini_hda_automation__validate_hda` → `houdini_hda_automation__cook_top_network` / `houdini_hda_automation__execute_rop_chain` |
| Project + shot packaging | `load_skill("houdini-pipeline")` → `houdini_pipeline__set_project` → `houdini_pipeline__validate_scene` → `houdini_pipeline__collect_dependencies` → `houdini_pipeline__export_shot_package` |
| Develop & debug tools | `load_skill("houdini-dev")` → `houdini_dev__attach_project` → `houdini_dev__reload_modules` → `houdini_dev__run_entrypoint` → `houdini_dev__introspect_hom` / `houdini_dev__start_debugpy` |
| File-based automation | `load_skill("houdini-automation")` → `houdini_automation__run_python_file` |
| Motion FX & CHOPs | `load_skill("houdini-chops")` → `houdini_chops__create_chop_network` → `houdini_chops__create_motionclip` → `houdini_chops__apply_filter` → `houdini_chops__get_channel_info` → `houdini_chops__export_to_keyframes` |
| Audio-driven animation | `load_skill("houdini-chops")` → `houdini_chops__create_chop_network` → `houdini_chops__create_audio_driven` |
| Constrain transforms | `load_skill("houdini-constraints")` → `houdini_constraints__create_parent_constraint` / `create_blend_constraint` / `create_position_constraint` / `create_orient_constraint` → `houdini_constraints__list_constraints` → `houdini_constraints__delete_constraint` |
| KineFX character rig | `load_skill("houdini-kinefx")` → `houdini_kinefx__create_rig` → `houdini_kinefx__set_rig_pose` → `houdini_kinefx__capture_joints` → `houdini_kinefx__apply_mocap` |
| Escape hatch | `load_skill("houdini-scripting")` → `houdini_scripting__execute_python` (last resort) |
| Karma render setup | `load_skill("houdini-karma")` → `houdini_karma__configure_karma` → `houdini_karma__set_material_override` → `houdini_karma__configure_light_mixer` → `houdini_karma__set_image_output` |
| Husk CLI render | `load_skill("houdini-husk")` → `houdini_husk__create_snapshot` → `houdini_husk__create_checkpoint` → `houdini_husk__set_husk_options` → `houdini_husk__render_with_husk` |
| Render layers & AOVs | `load_skill("houdini-render")` → `houdini_render__create_render_layer` → `houdini_render__configure_aovs` → `houdini_render__get_render_stats` |
| Takes management | `load_skill("houdini-render")` → `houdini_render__manage_takes(action="create")` → `houdini_render__manage_takes(action="switch")` → `houdini_render__manage_takes(action="list")` |
