# dcc-mcp-houdini

<p align="center">
  <img src="docs/assets/dcc-mcp-houdini.svg" alt="DCC-MCP · HOUDINI" width="600">
</p>

## Agent workflow

AI agents should use the shared gateway through `dcc-mcp-cli`; IDE users may
continue to use the MCP endpoint. Prefer typed skills and tools over raw scripts.

### Install or update the CLI

`dcc-mcp-cli` is the preferred control path for every shell-capable agent. If
it is missing, ask the user before installing the latest official release:

```bash
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-core/main/scripts/install-cli.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-core/main/scripts/install-cli.ps1 | iex"
```

Keep an official build current through the release manifest:

```bash
dcc-mcp-cli update check
dcc-mcp-cli update apply
```

`update apply` downloads and stages the latest CLI for the next launch. It
does not update a running `dcc-mcp-server`; update that server in its own
environment.

```bash
dcc-mcp-cli dcc-types
dcc-mcp-cli list
dcc-mcp-cli search --query "<task>" --dcc-type houdini
dcc-mcp-cli describe <tool-slug>
dcc-mcp-cli call <tool-slug> --json '{"key":"value"}'
```

`dcc-types` reports release-catalog support; `list` reports live sessions. If a
tool belongs to an inactive progressive skill, call `dcc-mcp-cli load-skill <skill-name> --dcc-type houdini` before retrying. For post-task improvement,
attach a stable session id with `--meta-json`, query `dcc-mcp-cli stats --range 24h --session-id <task-id>`, then pass the bounded evidence to the
`review_skill_improvement` prompt from `dcc-mcp-skills-creator`.


[![CI](https://github.com/dcc-mcp/dcc-mcp-houdini/actions/workflows/ci.yml/badge.svg)](https://github.com/dcc-mcp/dcc-mcp-houdini/actions/workflows/ci.yml)
[![E2E](https://github.com/dcc-mcp/dcc-mcp-houdini/actions/workflows/e2e.yml/badge.svg)](https://github.com/dcc-mcp/dcc-mcp-houdini/actions/workflows/e2e.yml)
[![Release](https://github.com/dcc-mcp/dcc-mcp-houdini/actions/workflows/release.yml/badge.svg)](https://github.com/dcc-mcp/dcc-mcp-houdini/actions/workflows/release.yml)
[![PyPI](https://img.shields.io/pypi/v/dcc-mcp-houdini.svg)](https://pypi.org/project/dcc-mcp-houdini/)
[![Python](https://img.shields.io/badge/python-3.7%2B-blue.svg)](pyproject.toml)
[![Downloads](https://img.shields.io/github/downloads/dcc-mcp/dcc-mcp-houdini/total.svg)](https://github.com/dcc-mcp/dcc-mcp-houdini/releases)
[![License](https://img.shields.io/github/license/dcc-mcp/dcc-mcp-houdini.svg)](LICENSE)
[![Release Assets](https://img.shields.io/github/v/release/dcc-mcp/dcc-mcp-houdini?label=github%20release)](https://github.com/dcc-mcp/dcc-mcp-houdini/releases)

SideFX Houdini adapter for the DCC Model Context Protocol (MCP) ecosystem.
It embeds a Streamable HTTP MCP server inside Houdini/hython and exposes
skills-first Houdini automation tools to agents.

## Six-DCC production showcase

![Procedural Houdini portal particles in the six-DCC showcase](docs/showcase/six-dcc-portal-particles.png)

This image is a real Blender render of a Houdini-authored animated effect.
In the tested six-instance workflow, Maya supplied the animated IK/FK rig,
3ds Max baked and re-exported the character, Houdini 21 generated 420
procedural particle instances and a 48-frame Alembic cache, and a second
Houdini GUI instance re-imported that cache before Blender assembled the final
shot. The rock asset came from the no-token `dcc-asset-polyhaven` marketplace
skill and is CC0-1.0.

## Features

- Embedded MCP Streamable HTTP server inside Houdini (OS-assigned instance port)
- Auto-gateway with first-wins election (gateway port 9765)
- Progressive skill loading (discover → load → unload)
- Houdini Python (`hython`) and interactive UI-thread dispatch
- Python 3.7+ package metadata for older Houdini runtimes
- Bundled skills for scripting, scene inspection, node authoring, HDA execution, and automation
- Wheel, sdist, and Houdini quickinstall ZIP release assets
- Prometheus metrics endpoint (`/metrics`), job persistence, and workflow engine support
- Optional licensed Houdini Docker E2E workflow

## Agent install (recommended)

Let your AI agent do the setup. In an MCP-capable agent (Cursor, Claude, etc.),
just say:

> 帮我参考 dcc-mcp/dcc-mcp-houdini/install.md 去安装

The agent reads [`install.md`](install.md), runs the
`dcc-mcp-houdini-setup` skill to install dependencies into Houdini's `hython`,
generates an MCP host config, guides the Houdini package startup hooks
step, and runs a smoke prompt to confirm the connection.

## Installation

### Release Wheel

```bash
pip install dcc-mcp-houdini
```

For an unreleased GitHub asset, install a release wheel directly:

```bash
pip install https://github.com/dcc-mcp/dcc-mcp-houdini/releases/download/v0.9.1/dcc_mcp_houdini-0.9.1-py3-none-any.whl
```

### Houdini Quickinstall ZIP

Download `dcc_mcp_houdini_quickinstall_<platform>_v<version>.zip` from
[GitHub Releases](https://github.com/dcc-mcp/dcc-mcp-houdini/releases), extract
it to a stable folder, then run:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -HoudiniVersion 20.5
```

For an isolated or custom package location, pass `-PackagesDir` explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -HoudiniVersion 20.5 -PackagesDir C:\temp\houdini-packages
```

`DCC_MCP_HOUDINI_PACKAGES_DIR` provides the same override on every platform;
on Windows, the explicit `-PackagesDir` argument takes precedence. Changing the
`HOME` environment variable inside PowerShell does not redirect its automatic
`$HOME` variable, so use this override for deterministic isolated installs.

On Linux/macOS:

```bash
chmod +x install.sh
./install.sh 20.5
```

The package writes a Houdini package JSON into the user preferences folder.
`scripts/123.py` handles an empty startup and `scripts/456.py` handles a loaded
scene; both reuse one bootstrap that extracts bundled wheels into `vendor/` and
starts the MCP server unless `DCC_MCP_HOUDINI_AUTOSTART=0`.

Isolated background ROP workers receive `DCC_MCP_BACKGROUND_RENDER=1` in their
child environment. Package and custom `123.py`/`456.py` startup hooks must skip
MCP adapter autostart when that marker is present; the parent Houdini environment
is not modified. Background render cancellation uses only live child-process
handles owned by the current adapter process; status-file PIDs are never used
as process ownership evidence.

## Usage

```python
import dcc_mcp_houdini

server = dcc_mcp_houdini.start_server()
print(server.mcp_url)  # Exact direct endpoint selected by the OS
```

`start_server()` is the interactive Houdini API and uses Houdini's budgeted
event-loop pump. Headless Hython must keep its owning thread available for HOM
work; launch the foreground pump instead:

```powershell
hython -m dcc_mcp_houdini
```

or call `dcc_mcp_houdini.serve_headless(...)` from a dedicated Hython
entrypoint. A plain headless `start_server()` fails before tools are registered
instead of silently executing HOM on an HTTP worker.

Hython cannot report a reliable HIP dirty state: context snapshots omit
`scene_saved`, while `validate_scene` returns `dirty: null`; GUI sessions report
the real boolean state. Destructive `open_scene` and `new_scene` calls fail
closed when that state is unknown unless the caller explicitly passes
`force=true`.

Default minimal mode (`DCC_MCP_MINIMAL=1`) loads only:

- `houdini-scripting`
- `houdini-scene`

Use progressive discovery for heavier tools:

```text
search_skills(query="hda")
load_skill("houdini-hda")
call houdini_hda__execute_hda
```

## Local MCP debug (Cursor / Claude)

See [`docs/guide/local-mcp-debug.md`](docs/guide/local-mcp-debug.md) and copy
[`examples/mcp/cursor-houdini-streamable-http.json`](examples/mcp/cursor-houdini-streamable-http.json)
into your MCP host config.

## Development

```bash
# Install dependencies
just dev

# Run tests
just test

# Lint
just lint-all

# Windows: build dcc-mcp-core with Houdini's Python and symlink
just houdini-version=20.5 houdini-dev-build-link-core-win

# Windows: start Houdini with debugpy
just houdini-version=20.5 houdini-dev-debug-win

# Build wheel + platform quickinstall package
just build-houdini-package platform=win64
```

## Release Publishing

The Release workflow publishes to PyPI when `release-please` creates a new
release. To backfill an existing GitHub release tag, run the Release workflow
manually with `tag_name=vX.Y.Z` and `publish_to_pypi=true`. Publishing uses
PyPI trusted publishing when configured, or `PYPI_API_TOKEN` when that secret is
available.

## Bundled Skills (30 packages, 185 tools)

Full authoritative index with ready-made task chains: `src/dcc_mcp_houdini/skills/SKILLS_INDEX.md`

### bootstrap (default loaded)
| Skill | Tools |
|-------|-------|
| `houdini-scripting` | `execute_python`, `get_session_info` |

### scene (partial default — `houdini-scene` only)
| Skill | Tools | Load |
|-------|-------|------|
| `houdini-scene` | `get_scene_info`, `list_obj_nodes`, `list_child_nodes`, `get_node_info` | default |
| `houdini-scene-edit` | `new_scene`, `open_scene`, `save_scene`, `get_selection`, `set_selection`, `find_nodes`, `list_cameras`, `get_bounding_box` | on demand |

### authoring (load on demand)
| Skill | Tools |
|-------|-------|
| `houdini-nodes` | `create_node`, `set_node_parms`, `connect_nodes`, `cook_node`, `layout_children`, `delete_node` |
| `houdini-object-ops` | `rename_node`, `duplicate_node`, `parent_node`, `set_node_flags`, `set_node_lock`, `get_transform`, `set_transform` |
| `houdini-parameters` | `list_parms`, `get_parms`, `get_parm_templates`, `get_expression`, `set_parms`, `add_spare_parm`, `remove_spare_parm`, `set_expression`, `clear_expression` |
| `houdini-node-graph` | `get_connections`, `connect_input`, `disconnect_input` |
| `houdini-geometry` | `create_primitive`, `get_geometry_info`, `list_attributes`, `list_groups`, `get_cook_status` |
| `houdini-mesh-ops` | `transform_geometry`, `merge_geometry`, `blast_geometry`, `group_geometry`, `add_normals`, `triangulate_geometry`, `convert_geometry` |
| `houdini-camera-light` | `list_cameras`, `create_camera`, `update_camera`, `frame_view`, `get_view_state`, `create_light`, `update_light` |
| `houdini-materials` | `create_material`, `assign_material`, `build_materialx_pbr`, `validate_materialx_pbr` |
| `houdini-lookdev` | `list_materials`, `list_assignments`, `get_material_parms`, `set_material_parms`, `get_shader_connections`, `connect_shader`, `disconnect_shader`, `reset_material`, `save_preset`, `list_presets`, `load_preset`, `delete_preset` |
| `houdini-hda` | `install_hda_file`, `list_hda_definitions`, `execute_hda`, `save_node_as_hda`, `promote_hda_parameters`, `author_hda_interface`, `publish_hda_library`, `validate_hda_contract`, `update_hda_definition`, `sync_hda_instance` |
| `houdini-chops` | `create_chop_network`, `create_motionclip`, `create_audio_driven`, `apply_filter`, `export_to_keyframes`, `get_channel_info` |
| `houdini-constraints` | `create_parent_constraint`, `create_blend_constraint`, `create_position_constraint`, `create_orient_constraint`, `list_constraints`, `delete_constraint` |
| `houdini-export-preset` | `list_export_presets`, `save_export_preset`, `load_export_preset`, `delete_export_preset` |
| `houdini-kinefx` | `create_rig`, `set_rig_pose`, `capture_joints`, `apply_mocap` |
| `houdini-light-rig` | `create_three_point_light_rig`, `create_area_softbox`, `create_hdri_world`, `list_light_rigs`, `set_light_rig_intensity`, `aim_light_at_object`, `group_lights`, `set_render_view_transform`, `get_lighting_summary` |
| `houdini-material-library` | `save_material_preset`, `list_material_presets`, `load_material_preset`, `delete_material_preset`, `get_shader_assignment`, `get_material_connections`, `set_material_attribute`, `assign_texture`, `list_images`, `reload_image`, `list_color_spaces`, `set_color_management` |
| `houdini-texture-bake` | `list_bake_targets`, `bake_textures`, `bake_ambient_occlusion`, `bake_lighting`, `transfer_maps` |

### interchange (load on demand)
| Skill | Tools |
|-------|-------|
| `houdini-interchange` | `probe_file`, `import_geometry`, `export_geometry`, `export_alembic`, `export_fbx`, `export_usd` |
| `houdini-import-to-scene` | `import_to_scene` |

### pipeline (load on demand)
| Skill | Tools |
|-------|-------|
| `houdini-render` | `capture_viewport`, `flipbook`, `get_render_settings`, `set_render_settings`, `validate_karma_stage`, `render_rop`, `get_render_job`, `finalize_render_outputs`, `cancel_render_job`, `create_render_layer`, `configure_aovs`, `manage_takes`, `get_render_stats` |
| `houdini-karma` | `configure_karma`, `set_material_override`, `configure_light_mixer`, `set_image_output` |
| `houdini-husk` | `render_with_husk`, `create_checkpoint`, `create_snapshot`, `set_husk_options` |
| `houdini-animation` | `get_timeline`, `set_timeline`, `set_keyframe`, `get_keyframes`, `delete_keyframes`, `list_animated_parms`, `validate_loop_contract`, `get_channel_info`, `export_channels`, `import_channels`, `bake_channels`, `cache_simulation` |
| `houdini-hda-automation` | `scan_hda_libraries`, `inspect_hda_definition`, `instantiate_hda`, `validate_hda`, `cook_top_network`, `execute_rop_chain` |
| `houdini-pipeline` | `set_project`, `get_project`, `tag_asset_metadata`, `get_asset_metadata`, `validate_scene`, `collect_dependencies`, `export_shot_package` |
| `houdini-dev` | `attach_project`, `reload_modules`, `run_entrypoint`, `run_script`, `start_debugpy`, `introspect_hom`, `ui_snapshot`, `ui_action` |
| `houdini-automation` | `run_python_file`, `set_frame_range`, `save_hip_file`, `load_hip_file`, `build_node_chain` |

## CI and Houdini Docker

Normal CI runs without Houdini installed: unit tests, skill validation, Python
3.7 syntax checks, wheel/sdist build, and quickinstall ZIP assembly.

Live Houdini E2E is in `.github/workflows/e2e.yml`. It defaults to
`sabjorn/hbuild-worker:21.0.559-base` and runs only when SideFX licensing
secrets are configured. See [`docs/ci/houdini-docker.md`](docs/ci/houdini-docker.md).

## Project Structure

```
dcc-mcp-houdini/
├── src/dcc_mcp_houdini/        # Python package and bundled skills
├── packaging/                  # Quickinstall ZIP assembly
├── tests/                      # Unit and packaging tests
├── tools/                      # Dev, lint, and syntax scripts
├── examples/                   # Usage examples
├── docs/                       # Guides and CI notes
├── justfile                    # Task runner
└── pyproject.toml              # Build config
```

## Requirements

- Houdini with Python 3.7+ (`hython` or interactive Houdini)
- `dcc-mcp-core >= 0.19.70`
- Quickinstall bundles the latest non-prerelease `dcc-mcp-core >= 0.19.70,<1.0.0` by default, or the validated `core_version` passed to a release backfill; no old-core pin is active.
- See `pyproject.toml` for full dependencies

## License

MIT
