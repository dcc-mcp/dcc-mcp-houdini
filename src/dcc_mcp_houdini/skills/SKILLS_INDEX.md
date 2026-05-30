# Houdini Bundled Skills Index

Progressive loading stages for `dcc-mcp-houdini`. Minimal mode loads **bootstrap + scene** at startup.

| Stage | Skills | Default loaded |
|-------|--------|----------------|
| `bootstrap` | `houdini-scripting` | yes |
| `scene` | `houdini-scene`, `houdini-scene-edit` | `houdini-scene` only |
| `authoring` | `houdini-nodes`, `houdini-object-ops`, `houdini-parameters`, `houdini-node-graph`, `houdini-geometry`, `houdini-mesh-ops`, `houdini-camera-light`, `houdini-materials`, `houdini-lookdev`, `houdini-hda` | no |
| `interchange` | `houdini-interchange` | no |
| `pipeline` | `houdini-render`, `houdini-animation`, `houdini-automation` | no |

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
| Render & verify | `load_skill("houdini-render")` → `houdini_render__set_render_settings` → `houdini_render__capture_viewport` → `houdini_render__render_rop` |
| Create and assign material | `load_skill("houdini-materials")` → `houdini_materials__create_material` → `houdini_materials__assign_material` |
| Animate & bake | `load_skill("houdini-animation")` → `houdini_animation__set_timeline` → `houdini_animation__set_keyframe` → `houdini_animation__get_keyframes` → `houdini_animation__bake_channels` / `houdini_animation__cache_simulation` |
| Lookdev & shader networks | `load_skill("houdini-lookdev")` → `houdini_lookdev__list_materials` → `houdini_lookdev__get_material_parms` → `houdini_lookdev__set_material_parms` → `houdini_lookdev__save_preset` / `houdini_lookdev__load_preset` |
| Run an HDA | `load_skill("houdini-hda")` → `houdini_hda__execute_hda` |
| Probe / import / export files | `load_skill("houdini-interchange")` → `houdini_interchange__probe_file` → `houdini_interchange__import_geometry` / `houdini_interchange__export_geometry` / `export_alembic` / `export_fbx` / `export_usd` |
| File-based automation | `load_skill("houdini-automation")` → `houdini_automation__run_python_file` |
| Escape hatch | `load_skill("houdini-scripting")` → `houdini_scripting__execute_python` (last resort) |
