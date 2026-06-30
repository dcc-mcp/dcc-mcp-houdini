# GEMINI.md — Google Gemini / Vertex AI Integration Guide

> Gemini-specific integration notes for `dcc-mcp-houdini`.
> For the full project map, see [AGENTS.md](AGENTS.md).

---

## What This Project Does

`dcc-mcp-houdini` embeds an MCP Streamable HTTP server directly inside SideFX Houdini. Gemini (via an MCP-compatible client or custom integration) can discover and invoke 180+ Houdini tools across 30 skill packages over HTTP.

---

## Integration Setup

If your Gemini client supports MCP over HTTP, configure:

```
Endpoint: http://127.0.0.1:8765/mcp
Protocol: MCP Streamable HTTP (2025-03-26 spec)
```

For multi-instance gateway mode:
```
Endpoint: http://127.0.0.1:9765/mcp
```

---

## Gemini-Specific Tips

- **Code-first workflows:** Gemini excels at generating structured Houdini networks. Ask it to build complete SOP chains with `houdini_nodes__create_node` → `connect_nodes` → `cook_node`.
- **Lookdev & materials:** Gemini's structured output handling makes it ideal for `houdini-lookdev` chains — set material parameters, save/load presets.
- **Viewport capture:** Feed `capture_viewport` base64 PNGs back to Gemini for visual state verification.
- **Pipeline automation:** Use `houdini-pipeline` skills for shot packaging and scene validation workflows.

---

## Quick Test Prompts

> "Create a camera and a three-point lighting setup"
> "List all materials in the scene and export their presets"
> "Import an alembic cache from /path/to/file.abc"
> "Validate the scene and collect all dependencies"

---

## See Also

- [AGENTS.md](AGENTS.md) — Shared agent navigation map
- [llms.txt](llms.txt) — One-page core reference
- [README.md](README.md) — Human-facing installation and overview
