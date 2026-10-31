"""Auto-start the MCP server when Houdini launches (GUI sessions only).

Install (pick one):

* Windows user scripts:
  ``%USERPROFILE%\\Documents\\houdini20.5\\scripts\\123.py``
* Or set ``HOUDINI_PATH`` / ``HS/site`` to a folder containing this file as ``123.py``

Prefer the installer-managed hook (``dcc-mcp-houdini-setup``), which deploys
``scripts/123.py`` / ``456.py`` / ``pythonX.Ylibs/uiready.py`` through
``scripts/dcc_mcp_houdini_bootstrap.py``. This file is the manual fallback for
users who copy the hook by hand, and mirrors the installer's guards.

Headless Hython and background-render workers never start a GUI server here:
Houdini also runs ``123.py`` for those sessions, so the hook skips when
``hou.isUIAvailable()`` is false or when ``DCC_MCP_BACKGROUND_RENDER=1`` is in
the child environment. For an MCP server in a headless session run
``hython -m dcc_mcp_houdini`` (or ``hython examples/houdini_bootstrap.py``)
instead; that foreground pump keeps HOM calls on Hython's owning thread.

Set ``DCC_MCP_HOUDINI_AUTOSTART=0`` to disable GUI autostart entirely.
"""

from __future__ import annotations

import os

# Values that disable the opt-out flag (kept in sync with the installer hook).
_DISABLED_AUTOSTART = ("0", "false", "no", "off")


def _skip_autostart() -> bool:
    """Return True for sessions that must not start the GUI MCP server.

    Order mirrors ``scripts/dcc_mcp_houdini_bootstrap.py``: the background-render
    marker and the explicit opt-out are checked before ``hou`` is imported, so a
    background worker never even probes the GUI state.
    """
    if os.environ.get("DCC_MCP_BACKGROUND_RENDER") == "1":
        return True
    raw = os.environ.get("DCC_MCP_HOUDINI_AUTOSTART", "1").strip().lower()
    return raw in _DISABLED_AUTOSTART


if not _skip_autostart():
    try:
        import hou

        if hou.isUIAvailable():
            import dcc_mcp_houdini

            server = dcc_mcp_houdini.start_server()
            print(f"[dcc-mcp-houdini] auto-started: {server.mcp_url}")
        else:
            print(
                "[dcc-mcp-houdini] headless startup hook skipped; run "
                "`hython -m dcc_mcp_houdini` (or examples/houdini_bootstrap.py) "
                "for the foreground main-thread MCP pump"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[dcc-mcp-houdini] autostart failed: {exc}")
