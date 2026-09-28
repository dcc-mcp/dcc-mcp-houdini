# Environment variables

Reference table for every `DCC_MCP_*` variable the `dcc-mcp-houdini` adapter
reads. Source of truth for resolution logic is
`src/dcc_mcp_houdini/_env.py`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DCC_MCP_HOUDINI_PORT` | `0` | MCP instance port (`0` lets the OS choose) |
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

## Host-side paths

| Variable | Purpose |
|----------|---------|
| `DCC_MCP_HOUDINI_PACKAGES_DIR` | Override the Houdini packages directory on every platform (see `README.md`) |

## Autostart opt-out

Set `DCC_MCP_HOUDINI_AUTOSTART=0` to stop the `123.py` startup hook from
launching the MCP server. See `README.md` for the marker-file protocol used to
suppress autostart in child Houdini environments.
