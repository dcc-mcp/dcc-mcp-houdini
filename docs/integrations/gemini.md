# Google Gemini / Vertex AI integration

> Gemini-specific integration notes for `dcc-mcp-houdini`.
> For the full project map, see [`AGENTS.md`](../../AGENTS.md).

## What this project does

`dcc-mcp-houdini` embeds an MCP Streamable HTTP server directly inside SideFX
Houdini. Gemini (via an MCP-compatible client or custom integration) can
discover and invoke the bundled Houdini tools over HTTP.

## Integration setup

If your Gemini client supports MCP over HTTP, configure:

```
Gateway endpoint: http://127.0.0.1:9765/mcp
Protocol: MCP Streamable HTTP (2025-03-26 spec)
```

For multi-instance gateway mode:

```
Endpoint: http://127.0.0.1:9765/mcp
```

## Gemini-specific tips

- **Code-first workflows:** Gemini excels at generating structured Houdini
  networks. Ask it to build complete SOP chains with
  `houdini_nodes__create_node` → `connect_nodes` → `cook_node`.
- **Lookdev & materials:** Gemini's structured output handling makes it ideal
  for `houdini-lookdev` chains — set material parameters, save/load presets.
- **Viewport capture:** feed `capture_viewport` base64 PNGs back to Gemini for
  visual state verification.
- **Pipeline automation:** use `houdini-pipeline` skills for shot packaging and
  scene validation workflows.

## Quick test prompts

> "Create a camera and a three-point lighting setup"
> "List all materials in the scene and export their presets"
> "Import an alembic cache from /path/to/file.abc"
> "Validate the scene and collect all dependencies"

## See also

- [`AGENTS.md`](../../AGENTS.md) — shared agent navigation map
- [`../integrations/claude.md`](claude.md) — Claude integration notes
- [`llms.txt`](../../llms.txt) — one-page core reference
- [`README.md`](../../README.md) — human-facing installation and overview
