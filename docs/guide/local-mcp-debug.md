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
print(server.mcp_url)  # Exact direct endpoint selected by the OS
```

Every Houdini instance binds an OS-assigned port and registers its exact URL.
The gateway remains on stable port **9765**, so agents and the CLI can discover
multiple simultaneous Houdini instances without hard-coded instance ports.

For auto-start in **GUI** sessions, prefer the installer-managed hook from
`dcc-mcp-houdini-setup`, which deploys `scripts/123.py` / `456.py` /
`pythonX.Ylibs/uiready.py` through `scripts/dcc_mcp_houdini_bootstrap.py`. If you
install by hand instead, copy [`examples/houdini_123.py`](../../examples/houdini_123.py)
into your Houdini scripts path (see file header).

The hook is GUI-only. Houdini also runs `123.py` for headless `hython` and
background ROP workers, so the example skips autostart when
`hou.isUIAvailable()` is false or `DCC_MCP_BACKGROUND_RENDER=1`; it never emits
an `autostart failed` line in those sessions. Set `DCC_MCP_HOUDINI_AUTOSTART=0`
to disable GUI autostart entirely. For an MCP server in a headless session use
[section 5](#5-headless-smoke-hython-no-ui) (`hython -m dcc_mcp_houdini`), not
this GUI hook.

## 3. Connect Cursor (Streamable HTTP MCP)

1. Open **Cursor Settings → MCP**.
2. Add a server pointing at your Houdini MCP URL.

Copy from [`examples/mcp/cursor-houdini-streamable-http.json`](../../examples/mcp/cursor-houdini-streamable-http.json):

```json
{
  "mcpServers": {
    "houdini-local": {
      "url": "http://127.0.0.1:9765/mcp"
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

Prints `MCP_URL=...` and then drives the bounded MCP queue on Hython's owning
thread. Do not replace this foreground bootstrap with `start_server()` plus a
sleep loop: that loop cannot satisfy main-thread affinity for HOM tools.

A fresh headless instance starts in progressive minimal mode (`DCC_MCP_MINIMAL=1`,
only `houdini-scripting` + `houdini-scene` loaded). Until `load_skill("houdini-automation")`
(or another tool's skill) is called, a heavier tool returns `ACTION_NOT_FOUND`.
That means "load the skill first", not a broken adapter — use `search_skills` /
`load_skill` to bring up the tools a job needs before its first useful call.

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
