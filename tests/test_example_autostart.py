"""The legacy user-script example must only start a GUI server in GUI sessions.

Regression for GH#365 Finding 1: the documented ``examples/houdini_123.py`` used
to call the GUI ``start_server()`` from every session Houdini runs ``123.py`` for
(headless Hython and background ROP workers), producing a false
``autostart failed`` line in every background render log. The example must now
mirror the installer-managed hook: skip on headless / background-render / opt-out.
"""

from __future__ import annotations

import contextlib
import io
import os
import runpy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "houdini_123.py"


class AutostartExampleTests(unittest.TestCase):
    def run_example(self, ui_available, *, autostart="1", background=None):
        start = Mock(return_value=SimpleNamespace(mcp_url="http://127.0.0.1:12345/mcp"))
        hou = SimpleNamespace(isUIAvailable=Mock(return_value=ui_available))
        adapter = SimpleNamespace(start_server=start)
        # Isolate env so a leaked DCC_MCP_BACKGROUND_RENDER from the parent
        # process cannot make a GUI case skip for the wrong reason.
        env = {"DCC_MCP_HOUDINI_AUTOSTART": autostart}
        if background is not None:
            env["DCC_MCP_BACKGROUND_RENDER"] = background
        stdout = io.StringIO()
        with patch.dict(os.environ, env, clear=True):
            with patch.dict(sys.modules, {"hou": hou, "dcc_mcp_houdini": adapter}):
                with contextlib.redirect_stdout(stdout):
                    runpy.run_path(str(EXAMPLE), run_name="__startup_example__")
        return hou, start, stdout.getvalue()

    def test_gui_keeps_normal_startup(self):
        """A GUI session still auto-starts the MCP server (no regression)."""
        hou, start, output = self.run_example(True)
        hou.isUIAvailable.assert_called_once_with()
        start.assert_called_once_with()
        self.assertIn("auto-started", output)
        self.assertNotIn("autostart failed", output)

    def test_headless_does_not_start_interactive_server(self):
        """Headless Hython skips the GUI server with at most one info line."""
        hou, start, output = self.run_example(False)
        hou.isUIAvailable.assert_called_once_with()
        start.assert_not_called()
        self.assertNotIn("autostart failed", output)
        self.assertLessEqual(len(output.strip().splitlines()), 1)

    def test_background_render_skips_before_probing_hou(self):
        """DCC_MCP_BACKGROUND_RENDER=1 must skip even if a GUI reports available.

        The installer hook checks this marker before importing ``hou``; a
        background ROP worker must never start a GUI server or probe the UI.
        """
        hou, start, output = self.run_example(True, background="1")
        hou.isUIAvailable.assert_not_called()
        start.assert_not_called()
        self.assertNotIn("autostart failed", output)

    def test_background_render_skips_even_when_headless(self):
        """The marker wins regardless of the (unprobed) UI state."""
        hou, start, output = self.run_example(False, background="1")
        hou.isUIAvailable.assert_not_called()
        start.assert_not_called()
        self.assertNotIn("autostart failed", output)

    def test_disabled_does_not_probe_hou_or_start(self):
        """DCC_MCP_HOUDINI_AUTOSTART=0 still disables autostart."""
        hou, start, output = self.run_example(True, autostart="0")
        hou.isUIAvailable.assert_not_called()
        start.assert_not_called()
        self.assertNotIn("autostart failed", output)


if __name__ == "__main__":
    unittest.main()
