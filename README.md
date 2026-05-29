# dcc-mcp-houdini

[![CI](https://github.com/loonghao/dcc-mcp-houdini/actions/workflows/ci.yml/badge.svg)](https://github.com/loonghao/dcc-mcp-houdini/actions/workflows/ci.yml)
[![E2E](https://github.com/loonghao/dcc-mcp-houdini/actions/workflows/e2e.yml/badge.svg)](https://github.com/loonghao/dcc-mcp-houdini/actions/workflows/e2e.yml)
[![Release](https://github.com/loonghao/dcc-mcp-houdini/actions/workflows/release.yml/badge.svg)](https://github.com/loonghao/dcc-mcp-houdini/actions/workflows/release.yml)
[![PyPI](https://img.shields.io/pypi/v/dcc-mcp-houdini.svg)](https://pypi.org/project/dcc-mcp-houdini/)
[![Python](https://img.shields.io/badge/python-3.7%2B-blue.svg)](pyproject.toml)
[![Downloads](https://img.shields.io/github/downloads/loonghao/dcc-mcp-houdini/total.svg)](https://github.com/loonghao/dcc-mcp-houdini/releases)
[![License](https://img.shields.io/github/license/loonghao/dcc-mcp-houdini.svg)](LICENSE)
[![Release Assets](https://img.shields.io/github/v/release/loonghao/dcc-mcp-houdini?label=github%20release)](https://github.com/loonghao/dcc-mcp-houdini/releases)

SideFX Houdini adapter for the DCC Model Context Protocol (MCP) ecosystem.
It embeds a Streamable HTTP MCP server inside Houdini/hython and exposes
skills-first Houdini automation tools to agents.

## Features

- Embedded MCP Streamable HTTP server inside Houdini
- Auto-gateway with first-wins port competition (port 8765)
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

> 帮我参考 loonghao/dcc-mcp-houdini/install.md 去安装

The agent reads [`install.md`](install.md), runs the
`dcc-mcp-houdini-setup` skill to install dependencies into Houdini's `hython`,
generates an MCP host config, guides the Houdini package / `123.py` autostart
step, and runs a smoke prompt to confirm the connection.

## Installation

### Release Wheel

```bash
pip install dcc-mcp-houdini
```

For an unreleased GitHub asset, install a release wheel directly:

```bash
pip install https://github.com/loonghao/dcc-mcp-houdini/releases/download/v0.1.0/dcc_mcp_houdini-0.1.0-py3-none-any.whl
```

### Houdini Quickinstall ZIP

Download `dcc_mcp_houdini_quickinstall_<platform>_v<version>.zip` from
[GitHub Releases](https://github.com/loonghao/dcc-mcp-houdini/releases), extract
it to a stable folder, then run:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -HoudiniVersion 20.5
```

On Linux/macOS:

```bash
chmod +x install.sh
./install.sh 20.5
```

The package writes a Houdini package JSON into the user preferences folder.
On startup, `scripts/123.py` extracts bundled wheels into `vendor/` and starts
the MCP server unless `DCC_MCP_HOUDINI_AUTOSTART=0`.

## Usage

```python
import dcc_mcp_houdini

server = dcc_mcp_houdini.start_server()
print(server.mcp_url)  # http://127.0.0.1:8765/mcp
```

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

## Bundled Skills

| Skill | Stage | Tools |
|-------|-------|-------|
| `houdini-scripting` | bootstrap | `execute_python`, `get_session_info` |
| `houdini-scene` | scene | `get_scene_info`, `list_obj_nodes`, `list_child_nodes`, `get_node_info` |
| `houdini-nodes` | authoring | `create_node`, `set_node_parms`, `connect_nodes`, `cook_node`, `layout_children`, `delete_node` |
| `houdini-materials` | authoring | `create_material`, `assign_material` |
| `houdini-hda` | authoring | `install_hda_file`, `list_hda_definitions`, `execute_hda`, `save_node_as_hda` |
| `houdini-automation` | pipeline | `run_python_file`, `set_frame_range`, `save_hip_file`, `load_hip_file`, `build_node_chain` |

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
- `dcc-mcp-core >= 0.17.26`
- See `pyproject.toml` for full dependencies

## License

MIT
