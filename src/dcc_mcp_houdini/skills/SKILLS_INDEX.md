# Houdini Bundled Skills Index

Progressive loading stages for `dcc-mcp-houdini`. Minimal mode loads **bootstrap + scene** at startup.

| Stage | Skills | Default loaded |
|-------|--------|----------------|
| `bootstrap` | `houdini-scripting` | yes |
| `scene` | `houdini-scene`, `houdini-scene-edit` | `houdini-scene` only |
| `authoring` | `houdini-nodes`, `houdini-object-ops`, `houdini-parameters`, `houdini-node-graph`, `houdini-geometry`, `houdini-mesh-ops`, `houdini-materials`, `houdini-hda` | no |
| `interchange` | _(planned: USD, FBX, Alembic)_ | no |
| `pipeline` | `houdini-automation` | no |

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
| Create and assign material | `load_skill("houdini-materials")` → `houdini_materials__create_material` → `houdini_materials__assign_material` |
| Run an HDA | `load_skill("houdini-hda")` → `houdini_hda__execute_hda` |
| File-based automation | `load_skill("houdini-automation")` → `houdini_automation__run_python_file` |
| Escape hatch | `load_skill("houdini-scripting")` → `houdini_scripting__execute_python` (last resort) |
