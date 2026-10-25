"""The legacy user-script example must never start a GUI server in Hython."""

import os
import runpy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "houdini_123.py"


class AutostartExampleTests(unittest.TestCase):
    def run_example(self, ui_available, enabled="1"):
        start = Mock(return_value=SimpleNamespace(mcp_url="http://127.0.0.1:12345/mcp"))
        hou = SimpleNamespace(isUIAvailable=Mock(return_value=ui_available))
        adapter = SimpleNamespace(start_server=start)
        with patch.dict(os.environ, {"DCC_MCP_HOUDINI_AUTOSTART": enabled}):
            with patch.dict(sys.modules, {"hou": hou, "dcc_mcp_houdini": adapter}):
                runpy.run_path(str(EXAMPLE), run_name="__startup_example__")
        return hou, start

    def test_headless_does_not_start_interactive_server(self):
        hou, start = self.run_example(False)
        hou.isUIAvailable.assert_called_once_with()
        start.assert_not_called()

    def test_gui_keeps_normal_startup(self):
        _, start = self.run_example(True)
        start.assert_called_once_with()

    def test_disabled_does_not_probe_hou_or_start(self):
        hou, start = self.run_example(True, enabled="0")
        hou.isUIAvailable.assert_not_called()
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
