# Houdini Bundled Skills Index

Progressive loading stages for `dcc-mcp-houdini`. Minimal mode loads **bootstrap + scene** at startup.

| Stage | Skills | Default loaded |
|-------|--------|----------------|
| `bootstrap` | `houdini-scripting` | yes |
| `scene` | `houdini-scene` | yes |
| `authoring` | `houdini-nodes`, `houdini-materials`, `houdini-hda` | no |
| `interchange` | _(planned: USD, FBX, Alembic)_ | no |
| `pipeline` | `houdini-animation`, `houdini-automation` | no |

## Common chains

| Task | Chain |
|------|-------|
| Verify MCP session | `houdini_scripting__get_session_info` |
| Inspect hip | `houdini_scene__get_scene_info` → `houdini_scene__list_obj_nodes` |
| Build SOP/OBJ network | `load_skill("houdini-nodes")` → `houdini_nodes__create_node` → `houdini_nodes__set_node_parms` → `houdini_nodes__connect_nodes` → `houdini_nodes__cook_node` |
| Create and assign material | `load_skill("houdini-materials")` → `houdini_materials__create_material` → `houdini_materials__assign_material` |
| Animate & bake | `load_skill("houdini-animation")` → `houdini_animation__set_timeline` → `houdini_animation__set_keyframe` → `houdini_animation__get_keyframes` → `houdini_animation__bake_channels` / `houdini_animation__cache_simulation` |
| Run an HDA | `load_skill("houdini-hda")` → `houdini_hda__execute_hda` |
| File-based automation | `load_skill("houdini-automation")` → `houdini_automation__run_python_file` |
| Escape hatch | `load_skill("houdini-scripting")` → `houdini_scripting__execute_python` (last resort) |
