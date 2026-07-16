# MCP host configuration examples

## Cursor / Claude Desktop (Streamable HTTP)

| File | URL | When to use |
|------|-----|-------------|
| `cursor-houdini-streamable-http.json` | `http://127.0.0.1:9765/mcp` | Stable gateway that discovers all Houdini instances |

Set `DCC_MCP_HOUDINI_PORT` only when a fixed direct instance URL is required.

See [`docs/guide/local-mcp-debug.md`](../../docs/guide/local-mcp-debug.md) for the full dev-link + debugpy workflow.
