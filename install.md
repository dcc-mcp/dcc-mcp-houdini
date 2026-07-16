# dcc-mcp-houdini Agent Install

Use this page when an agent is asked to install or configure
`loonghao/dcc-mcp-houdini` for SideFX Houdini.

## Agent Instruction

If the user says "帮我参考 loonghao/dcc-mcp-houdini/install.md 去安装",
do this:

1. Read `skills/dcc-mcp-houdini-setup/SKILL.md`.
2. Run the setup script from the repository root.
3. Help the user install the Houdini package so `123.py` autostarts the server.
4. Configure the MCP host with the generated Streamable HTTP JSON.
5. Run the smoke prompt to prove the connection works.

## One Command

From the repository root:

```bash
python skills/dcc-mcp-houdini-setup/scripts/setup_dcc_mcp_houdini.py
```

For an end-user install from PyPI instead of this checkout:

```bash
python skills/dcc-mcp-houdini-setup/scripts/setup_dcc_mcp_houdini.py --source pypi
```

If `hython` is not auto-detected:

```bash
python skills/dcc-mcp-houdini-setup/scripts/setup_dcc_mcp_houdini.py --hython "C:\Program Files\Side Effects Software\Houdini 20.5.487\bin\hython.exe"
```

`hython` ships with Houdini. Typical locations:

- Windows: `C:\Program Files\Side Effects Software\Houdini X.Y.ZZZ\bin\hython.exe`
- macOS: `/Applications/Houdini/HoudiniX.Y.ZZZ/.../Resources/bin/hython`
- Linux: `/opt/hfsX.Y.ZZZ/bin/hython`

## Houdini Autostart Step

After the script finishes, the user must make the server start with Houdini.
The recommended path is the bundled Houdini package:

1. Install the Houdini package (quickinstall ZIP `install.ps1` / `install.sh`,
   or a `dcc_mcp_houdini.json` package file pointing at the package root).
2. The package adds `scripts/` to `HOUDINI_PATH`; on startup `123.py` extracts
   bundled wheels into `vendor/` and starts the MCP server unless
   `DCC_MCP_HOUDINI_AUTOSTART=0`.
3. Start Houdini and watch the console for the exact OS-assigned instance URL.

Agents should connect through the stable local gateway:

```text
http://127.0.0.1:9765/mcp
```

Multi-instance auto-gateway mode (`DCC_MCP_GATEWAY_PORT=9765`) uses:

```text
http://127.0.0.1:9765/mcp
```

You can also start the server manually from an `hython` session:

```python
import dcc_mcp_houdini
server = dcc_mcp_houdini.start_server()
print(server.mcp_url)  # Exact direct endpoint selected by the OS
```

## MCP Config

Use this JSON for Cursor, Claude Desktop, or any MCP Streamable HTTP host:

```json
{
  "mcpServers": {
    "houdini": {
      "url": "http://127.0.0.1:9765/mcp"
    }
  }
}
```

The setup script also writes config snippets and a smoke prompt under:

```text
.dcc-mcp/agent-setup/
```
