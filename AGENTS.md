# AGENTS.md — dcc-mcp-houdini

> Navigation map for AI agents. Detailed API → `llms.txt`.

## Quick Start (inside Houdini)

```python
import dcc_mcp_houdini
server = dcc_mcp_houdini.start_server()
# MCP URL: http://127.0.0.1:8765/mcp
```

## Skills-First Workflow

```
1. search_skills(query="scene") -> find a typed Houdini skill
2. load_skill("houdini-nodes") / load_skill("houdini-hda") when authoring tools are needed
3. call houdini_scene__get_scene_info / houdini_nodes__create_node / houdini_hda__execute_hda
4. use houdini_scripting__execute_python only when no typed skill fits
```

**Default minimal mode** (`DCC_MCP_MINIMAL=1`): only `houdini-scripting` + `houdini-scene` loaded at startup.

## Local Debug

| Step | Command |
|------|---------|
| Win dev link + core build | `just houdini-version=20.5 houdini-dev-build-link-core-win` |
| Launch Houdini | `just houdini-version=20.5 houdini-dev-debug-win` |
| Build release assets | `just build-houdini-package platform=win64` |
| Cursor MCP JSON | `examples/mcp/cursor-houdini-streamable-http.json` |
| Full guide | `docs/guide/local-mcp-debug.md` |
| Docker E2E notes | `docs/ci/houdini-docker.md` |

## Main-Thread Execution

Houdini `hou.*` APIs require the UI thread. The adapter wires:

- `BlockingDispatcher` + `HoudiniHost` → `hou.ui.addEventLoopCallback`
- Headless `hython` → inline / standalone dispatcher

## Skill authoring

When adding or changing bundled skills, load the project skill:

- **Cursor:** `.cursor/skills/dcc-mcp-skill-developer/SKILL.md`
- **Checklist:** `references/SKILL_AUTHORING_CHECKLIST.md` in that skill
- **Index:** `src/dcc_mcp_houdini/skills/SKILLS_INDEX.md`

## Bundled Skills

### bootstrap stage (default loaded)
| Skill | Tools |
|-------|-------|
| `houdini-scripting` | `execute_python`, `get_session_info` |

### scene stage (partial default — `houdini-scene` only)
| Skill | Tools | Load |
|-------|-------|------|
| `houdini-scene` | `get_scene_info`, `list_obj_nodes`, `list_child_nodes`, `get_node_info` | default |
| `houdini-scene-edit` | `new_scene`, `open_scene`, `save_scene`, `get_selection`, `set_selection`, `find_nodes`, `list_cameras`, `get_bounding_box` | on demand |

### authoring stage (load on demand)
| Skill | Tools |
|-------|-------|
| `houdini-nodes` | `create_node`, `set_node_parms`, `connect_nodes`, `cook_node`, `layout_children`, `delete_node` |
| `houdini-object-ops` | `rename_node`, `duplicate_node`, `parent_node`, `set_node_flags`, `set_node_lock`, `get_transform`, `set_transform` |
| `houdini-parameters` | `list_parms`, `get_parms`, `get_parm_templates`, `get_expression`, `set_parms`, `add_spare_parm`, `remove_spare_parm`, `set_expression`, `clear_expression` |
| `houdini-node-graph` | `get_connections`, `connect_input`, `disconnect_input` |
| `houdini-geometry` | `create_primitive`, `get_geometry_info`, `list_attributes`, `list_groups`, `get_cook_status` |
| `houdini-mesh-ops` | `transform_geometry`, `merge_geometry`, `blast_geometry`, `group_geometry`, `add_normals`, `triangulate_geometry`, `convert_geometry` |
| `houdini-camera-light` | `list_cameras`, `create_camera`, `update_camera`, `frame_view`, `get_view_state`, `create_light`, `update_light` |
| `houdini-materials` | `create_material`, `assign_material` |
| `houdini-lookdev` | `list_materials`, `list_assignments`, `get_material_parms`, `set_material_parms`, `get_shader_connections`, `connect_shader`, `disconnect_shader`, `reset_material`, `save_preset`, `list_presets`, `load_preset`, `delete_preset` |
| `houdini-hda` | `install_hda_file`, `list_hda_definitions`, `execute_hda`, `save_node_as_hda` |
| `houdini-chops` | `create_chop_network`, `create_motionclip`, `create_audio_driven`, `apply_filter`, `export_to_keyframes`, `get_channel_info` |
| `houdini-constraints` | `create_parent_constraint`, `create_blend_constraint`, `create_position_constraint`, `create_orient_constraint`, `list_constraints`, `delete_constraint` |
| `houdini-export-preset` | `list_export_presets`, `save_export_preset`, `load_export_preset`, `delete_export_preset` |
| `houdini-kinefx` | `create_rig`, `set_rig_pose`, `capture_joints`, `apply_mocap` |
| `houdini-light-rig` | `create_three_point_light_rig`, `create_area_softbox`, `create_hdri_world`, `list_light_rigs`, `set_light_rig_intensity`, `aim_light_at_object`, `group_lights`, `set_render_view_transform`, `get_lighting_summary` |
| `houdini-material-library` | `save_material_preset`, `list_material_presets`, `load_material_preset`, `delete_material_preset`, `get_shader_assignment`, `get_material_connections`, `set_material_attribute`, `assign_texture`, `list_images`, `reload_image`, `list_color_spaces`, `set_color_management` |
| `houdini-texture-bake` | `list_bake_targets`, `bake_textures`, `bake_ambient_occlusion`, `bake_lighting`, `transfer_maps` |

### interchange stage (load on demand)
| Skill | Tools |
|-------|-------|
| `houdini-interchange` | `probe_file`, `import_geometry`, `export_geometry`, `export_alembic`, `export_fbx`, `export_usd` |
| `houdini-import-to-scene` | `import_to_scene` |

### pipeline stage (load on demand)
| Skill | Tools |
|-------|-------|
| `houdini-render` | `capture_viewport`, `flipbook`, `get_render_settings`, `set_render_settings`, `render_rop`, `create_render_layer`, `configure_aovs`, `manage_takes`, `get_render_stats` |
| `houdini-karma` | `configure_karma`, `set_material_override`, `configure_light_mixer`, `set_image_output` |
| `houdini-husk` | `render_with_husk`, `create_checkpoint`, `create_snapshot`, `set_husk_options` |
| `houdini-animation` | `get_timeline`, `set_timeline`, `set_keyframe`, `get_keyframes`, `delete_keyframes`, `list_animated_parms`, `get_channel_info`, `export_channels`, `import_channels`, `bake_channels`, `cache_simulation` |
| `houdini-hda-automation` | `scan_hda_libraries`, `inspect_hda_definition`, `instantiate_hda`, `validate_hda`, `cook_top_network`, `execute_rop_chain` |
| `houdini-pipeline` | `set_project`, `get_project`, `tag_asset_metadata`, `get_asset_metadata`, `validate_scene`, `collect_dependencies`, `export_shot_package` |
| `houdini-dev` | `attach_project`, `reload_modules`, `run_entrypoint`, `run_script`, `start_debugpy`, `introspect_hom`, `ui_snapshot`, `ui_action` |
| `houdini-automation` | `run_python_file`, `set_frame_range`, `save_hip_file`, `load_hip_file`, `build_node_chain` |

**Total: 29 skill packages, 173 tools** — See `src/dcc_mcp_houdini/skills/SKILLS_INDEX.md` for the authoritative index and ready-made task→skill chains.

## Key Env Vars

| Variable | Default | Purpose |
|----------|---------|---------|
| `DCC_MCP_HOUDINI_PORT` | `8765` | MCP HTTP port |
| `DCC_MCP_GATEWAY_PORT` | `9765` | Gateway election |
| `DCC_MCP_MINIMAL` | `1` | Progressive loading |
| `DCC_MCP_HOUDINI_AUTOSTART` | `1` | Auto-start via `123.py` |
| `DCC_MCP_HOUDINI_READINESS_TIMEOUT_SECS` | — | Advisory readyz timeout |
| `DCC_MCP_HOUDINI_SKILL_PATHS` | — | Extra skill directories |
| `DCC_MCP_HOUDINI_METRICS` | `0` | Enable `/metrics` |
| `DCC_MCP_HOUDINI_ENABLE_WORKFLOWS` | `0` | Enable core workflow engine |
| `DCC_MCP_HOUDINI_JOB_STORAGE_PATH` | user data | Job DB path |
| `DCC_MCP_HOUDINI_RESOURCES` | `1` | Enable MCP resources |
| `DCC_MCP_HOUDINI_PROJECT_TOOLS` | `1` | Enable project state tools |
| `DCC_MCP_HOUDINI_QT_UI_INSPECTOR` | `1` | Enable Qt UI inspector |
| `DCC_MCP_HOUDINI_SEMANTIC_INDEX` | `0` | Enable semantic recall |
| `DCC_MCP_HOUDINI_SEMANTIC_EMBEDDER` | `hashed` | Embedder type |
| `DCC_MCP_HOUDINI_DEV_ROOTS` | — | Trusted project roots for dev skill |
| `DCC_MCP_HOUDINI_MATERIAL_PRESET_DIR` | user data | Material preset directory |
| `DCC_MCP_HOUDINI_HYTHON` | — | hython path for setup scripts |
| `DCC_MCP_SKILL_PATHS` | — | Extra skill paths (cross-adapter) |

## File Index

| Path | Role |
|------|------|
| `src/dcc_mcp_houdini/server.py` | `HoudiniMcpServer`, `start_server` |
| `src/dcc_mcp_houdini/host.py` | Main-thread pump via event loop |
| `src/dcc_mcp_houdini/dispatcher/` | Execution stack factory |
| `src/dcc_mcp_houdini/skills/` | Bundled skills |
| `packaging/assemble_houdini_package.py` | Quickinstall ZIP builder |
| `.github/workflows/e2e.yml` | Optional licensed Houdini Docker smoke |
| `tools/houdini-dev-build-link-core-win.ps1` | Windows dev link |
