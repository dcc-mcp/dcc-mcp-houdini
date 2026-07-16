# CLAUDE.md — Claude Desktop / Anthropic API Integration Guide

> Claude-specific integration notes for `dcc-mcp-houdini`.
> For the full project map, see [AGENTS.md](AGENTS.md).

---

## What This Project Does

`dcc-mcp-houdini` embeds an MCP Streamable HTTP server directly inside SideFX Houdini. Claude Desktop (or any Anthropic API client using MCP) can call 180+ Houdini tools across 30 skill packages over HTTP — scene inspection, node authoring, HDA execution, rendering, and more.

---

## Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "houdini": {
      "url": "http://127.0.0.1:9765/mcp"
    }
  }
}
```

**File locations:**
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

If running gateway mode, use `http://127.0.0.1:9765/mcp` instead.

Restart Claude Desktop after editing.

---

## Progressive Loading — Important for Claude

By default, `dcc-mcp-houdini` starts in **minimal mode** with only 2 skills loaded:
- `houdini-scripting`
- `houdini-scene`

**All other skills must be loaded on demand.** When Claude needs a tool from an unloaded skill:

1. Call `load_skill("houdini-nodes")` to expand the skill.
2. Then call the typed tool (e.g., `houdini_nodes__create_node`).

---

## Claude-Specific Tips

- **Viewport feedback:** Ask Claude to call `houdini_render__capture_viewport` after scene changes. The base64 PNG lets Claude "see" the current state.
- **Node networks:** Claude excels at building SOP/OBJ networks. Chain `create_node` → `set_node_parms` → `connect_nodes` → `cook_node`.
- **Code execution:** Prefer `search_skills` → `load_skill` → typed tools. Use `execute_python` only as last resort.
- **HDA automation:** Use `houdini_hda_automation__instantiate_hda` and `houdini_hda_automation__cook_top_network` for HDA workflows.
- **Cancellation:** Claude can send `notifications/cancelled` for long renders.

---

## Quick Test Prompts

> "List all OBJ nodes in the current Houdini scene"
> "Create a sphere, connect it to a null, and cook the network"
> "Capture the viewport so I can see the current state"
> "Load the animation skill and set a keyframe on the sphere's ty at frame 24"

---

## See Also

- [AGENTS.md](AGENTS.md) — Shared agent navigation map
- [llms.txt](llms.txt) — One-page core reference
- [README.md](README.md) — Human-facing installation and overview
