# MCP host configuration examples

## Cursor / Claude Desktop (Streamable HTTP)

| File | URL | When to use |
|------|-----|-------------|
| `cursor-houdini-streamable-http.json` | `http://127.0.0.1:8765/mcp` | Direct connection to the first Houdini MCP server |

If you run a standalone gateway on port **9765**, change the URL to `http://127.0.0.1:9765/mcp`.

See [`docs/guide/local-mcp-debug.md`](../../docs/guide/local-mcp-debug.md) for the full dev-link + debugpy workflow.
