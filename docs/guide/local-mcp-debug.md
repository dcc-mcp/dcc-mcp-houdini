# Local MCP + debugging (Houdini + Cursor / Claude)

Use this after a **dev link** (`just houdini-version=20.5 houdini-dev-build-link-core-win`) so an MCP host can call your live Houdini session, and optionally attach a **Python debugger**.

## 1. Build core + link the adapter (Windows)

From the `dcc-mcp-houdini` repo (with sibling `dcc-mcp-core`):

```powershell
just houdini-version=20.5 houdini-dev-build-link-core-win
```

This runs `maturin develop` for `dcc-mcp-core` with Houdini's `hython`, then junction-links `dcc_mcp_houdini` into Houdini's site-packages.

To rebuild core and launch Houdini in one step:

```powershell
just houdini-version=20.5 houdini-dev-debug-win
```

## 2. Start the MCP HTTP server inside Houdini

In the **Python Source Editor** (or a shelf tool):

```python
import dcc_mcp_houdini

server = dcc_mcp_houdini.start_server()
print(server.mcp_url)  # http://127.0.0.1:8765/mcp
```

The first Houdini instance to bind port **8765** becomes the **gateway** when auto-gateway is enabled (default). Additional instances register on ephemeral ports.

For auto-start on every session, copy [`examples/houdini_123.py`](../../examples/houdini_123.py) into your Houdini scripts path (see file header).

## 3. Connect Cursor (Streamable HTTP MCP)

1. Open **Cursor Settings → MCP**.
2. Add a server pointing at your Houdini MCP URL.

Copy from [`examples/mcp/cursor-houdini-streamable-http.json`](../../examples/mcp/cursor-houdini-streamable-http.json):

```json
{
  "mcpServers": {
    "houdini-local": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Use **`http://127.0.0.1:9765/mcp`** only when a separate gateway process owns that port and your Houdini instance registered with it.

3. Restart MCP / reload the window if tools do not appear.
4. In chat, try `search_skills`, `load_skill`, or call bundled tools such as `houdini_scripting__get_session_info`.

## 4. Python debugging (debugpy + Cursor / VS Code)

1. Install **debugpy** into Houdini's Python (once):

   ```powershell
   & "C:\Program Files\Side Effects Software\Houdini 20.5\bin\hython.exe" -m pip install debugpy
   ```

2. In Houdini Python, run once after startup:

   ```python
   import debugpy
   debugpy.listen(("127.0.0.1", 5678))
   print("[dcc-mcp-houdini] debugpy on 127.0.0.1:5678")
   ```

3. In **Cursor / VS Code**, use **Run and Debug → Python: Remote Attach** with host `127.0.0.1` and port `5678`.
4. Set breakpoints under `src/dcc_mcp_houdini/**/*.py` or skill scripts, then invoke the tool from MCP.

## 5. Headless smoke (hython, no UI)

```powershell
hython examples/houdini_bootstrap.py
```

Prints `MCP_URL=...` when the server starts in background mode.

## 6. Quick checklist

| Check | Action |
|-------|--------|
| MCP connection refused | Houdini running? `start_server()` called? Port free? |
| Tools missing | Minimal mode: call `load_skill("houdini-nodes")`, `load_skill("houdini-hda")`, or `load_skill("houdini-automation")` for heavier tools |
| Breakpoints never hit | Attach debugpy to the **same** Houdini process |
| `hou` import fails outside Houdini | Expected — run server inside Houdini or `hython` |

## Related

- Repo **AGENTS.md** — progressive loading, dispatcher, env vars
- [`examples/start_server.py`](../../examples/start_server.py) — copy-paste startup script
