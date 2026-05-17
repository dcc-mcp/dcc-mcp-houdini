# dcc-mcp-houdini

SideFX Houdini adapter for the DCC Model Context Protocol (MCP) ecosystem — exposes Houdini tools via MCP.

## Features

- Embedded MCP Streamable HTTP server inside Houdini
- Auto-gateway with first-wins port competition (port 8765)
- Progressive skill loading (discover → load → unload)
- Houdini Python (`hython`) integration
- Prometheus metrics endpoint (`/metrics`)
- Job persistence and workflow engine support

## Installation

```bash
# Install in editable mode for development
pip install -e ".[dev]"

# Or install from PyPI (when available)
pip install dcc-mcp-houdini
```

## Usage (inside Houdini Python)

```python
import dcc_mcp_houdini

# Start server (auto-detects Houdini version)
server = dcc_mcp_houdini.start_server()

# Progressive skill loading
n = server.discover_skills()        # scan paths, register metadata
server.load_skill("houdini-scene") # lazy-load a specific skill

# Get MCP URL for AI agent connection
handle = server.start()
print(handle.mcp_url())  # http://127.0.0.1:8765/mcp

# Stop server
dcc_mcp_houdini.stop_server()
```

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
```

## Project Structure

```
dcc-mcp-houdini/
├── src/dcc_mcp_houdini/   # Python package
├── tests/                  # Test suite
├── tools/                  # Dev scripts (link, unlink, status)
├── examples/               # Usage examples
├── justfile                # Task runner
└── pyproject.toml         # Build config
```

## Requirements

- Houdini 20.5+ (Python 3.9+)
- dcc-mcp-core >= 0.17.2
- See `pyproject.toml` for full dependencies

## License

MIT
