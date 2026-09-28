# Claude Desktop / Anthropic API integration

> Claude-specific integration notes for `dcc-mcp-houdini`.
> For the full project map, see [`AGENTS.md`](../../AGENTS.md).

## What this project does

`dcc-mcp-houdini` embeds an MCP Streamable HTTP server directly inside SideFX
Houdini. Claude Desktop (or any Anthropic API client using MCP) can call the
bundled Houdini tools over HTTP — scene inspection, node authoring, HDA
execution, rendering, and more.

## Claude Desktop configuration

Add to `claude_desktop_config.json` — this is the shared **gateway** endpoint on `9765`,
which auto-discovers the running Houdini instance:

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

To target a single Houdini instance directly instead of through the gateway, use the
OS-assigned URL printed by `server.mcp_url` (see [`AGENTS.md`](../../AGENTS.md)). It is
not a fixed port and changes on every launch.

Restart Claude Desktop after editing.

## Progressive loading

By default, `dcc-mcp-houdini` starts in **minimal mode** (`DCC_MCP_MINIMAL=1`)
with only 2 skills loaded:

- `houdini-scripting`
- `houdini-scene`

**All other skills must be loaded on demand.** When Claude needs a tool from an
unloaded skill:

1. Call `load_skill("houdini-nodes")` to expand the skill.
2. Then call the typed tool (e.g. `houdini_nodes__create_node`).

## Claude-specific tips

- **Viewport feedback:** ask Claude to call `houdini_render__capture_viewport`
  after scene changes. The base64 PNG lets Claude "see" the current state.
- **Node networks:** Claude excels at building SOP/OBJ networks. Chain
  `create_node` → `set_node_parms` → `connect_nodes` → `cook_node`.
- **Code execution:** prefer `search_skills` → `load_skill` → typed tools. Use
  `execute_python` only as last resort.
- **HDA automation:** use `houdini_hda_automation__instantiate_hda` and
  `houdini_hda_automation__cook_top_network` for HDA workflows.
- **Cancellation:** Claude can send `notifications/cancelled` for long renders.

## Quick test prompts

> "List all OBJ nodes in the current Houdini scene"
> "Create a sphere, connect it to a null, and cook the network"
> "Capture the viewport so I can see the current state"
> "Load the animation skill and set a keyframe on the sphere's ty at frame 24"

## See also

- [`AGENTS.md`](../../AGENTS.md) — shared agent navigation map
- [`../integrations/gemini.md`](gemini.md) — Gemini integration notes
- [`llms.txt`](../../llms.txt) — one-page core reference
- [`README.md`](../../README.md) — human-facing installation and overview
