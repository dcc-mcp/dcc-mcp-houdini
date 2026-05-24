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

| Skill | Tools |
|-------|-------|
| `houdini-scripting` | `execute_python`, `get_session_info` |
| `houdini-scene` | `get_scene_info`, `list_obj_nodes`, `list_child_nodes`, `get_node_info` |
| `houdini-nodes` | `create_node`, `set_node_parms`, `connect_nodes`, `cook_node`, `layout_children`, `delete_node` |
| `houdini-materials` | `create_material`, `assign_material` |
| `houdini-hda` | `install_hda_file`, `list_hda_definitions`, `execute_hda`, `save_node_as_hda` |
| `houdini-automation` | `run_python_file`, `set_frame_range`, `save_hip_file`, `load_hip_file`, `build_node_chain` |

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
