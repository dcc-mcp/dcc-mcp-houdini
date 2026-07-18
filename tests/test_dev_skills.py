"""Mock-hou unit tests for the houdini-dev skill (headless-safe)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-dev" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"dev_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class TestDevProject:
    def test_attach_project_missing(self, tmp_path) -> None:
        mod = _load_script("attach_project.py")
        result = mod.attach_project(str(tmp_path / "nope"))
        assert result["success"] is False

    def test_attach_project_adds_to_syspath(self, tmp_path) -> None:
        mod = _load_script("attach_project.py")
        result = mod.attach_project(str(tmp_path))
        assert result["success"] is True
        assert str(tmp_path) in sys.path
        sys.path.remove(str(tmp_path))

    def test_attach_project_respects_dev_roots(self, tmp_path, monkeypatch) -> None:
        mod = _load_script("attach_project.py")
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        monkeypatch.setenv("DCC_MCP_HOUDINI_DEV_ROOTS", str(allowed))
        result = mod.attach_project(str(other))
        assert result["success"] is False

    def test_reload_modules_requires_target(self) -> None:
        mod = _load_script("reload_modules.py")
        result = mod.reload_modules()
        assert result["success"] is False

    def test_reload_modules_purges_prefix(self) -> None:
        mod = _load_script("reload_modules.py")
        sys.modules["fake_pkg"] = ModuleType("fake_pkg")
        sys.modules["fake_pkg.sub"] = ModuleType("fake_pkg.sub")
        result = mod.reload_modules(prefix="fake_pkg")
        assert result["success"] is True
        assert "fake_pkg.sub" in result["context"]["purged"]
        assert "fake_pkg" not in sys.modules


class TestDevRun:
    def test_run_entrypoint_captures_output(self, tmp_path) -> None:
        mod = _load_script("run_entrypoint.py")
        pkg_dir = tmp_path / "demo_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "mod.py").write_text("def go(x):\n    print('hello', x)\n    return x * 2\n")
        sys.path.insert(0, str(tmp_path))
        try:
            result = mod.run_entrypoint("demo_pkg.mod:go", args=[3], reload=False)
        finally:
            sys.path.remove(str(tmp_path))
            for name in list(sys.modules):
                if name.startswith("demo_pkg"):
                    sys.modules.pop(name, None)
        assert result["success"] is True
        assert "hello 3" in result["context"]["stdout"]
        assert result["context"]["result_repr"] == "6"

    def test_run_entrypoint_invalid(self) -> None:
        mod = _load_script("run_entrypoint.py")
        result = mod.run_entrypoint("notanentrypoint")
        assert result["success"] is False

    def test_run_script_captures_and_traceback(self, tmp_path) -> None:
        mod = _load_script("run_script.py")
        good = tmp_path / "ok.py"
        good.write_text("print('ran ok')\n")
        ok_result = mod.run_script(str(good))
        assert ok_result["success"] is True
        assert "ran ok" in ok_result["context"]["stdout"]

        bad = tmp_path / "boom.py"
        bad.write_text("raise ValueError('boom')\n")
        bad_result = mod.run_script(str(bad))
        assert bad_result["success"] is False
        assert "boom" in bad_result["context"]["traceback"]


class TestDevDebug:
    def test_start_debugpy_missing_package(self) -> None:
        mod = _load_script("start_debugpy.py")
        with patch.dict(sys.modules, {"debugpy": None}):
            result = mod.start_debugpy()
        assert result["success"] is False

    def test_start_debugpy_and_already_running(self) -> None:
        mod = _load_script("start_debugpy.py")
        fake_debugpy = MagicMock()
        with patch.dict(sys.modules, {"debugpy": fake_debugpy}):
            first = mod.start_debugpy(port=5999)
            second = mod.start_debugpy(port=5999)
        assert first["success"] is True
        assert first["context"]["already_running"] is False
        fake_debugpy.listen.assert_called_once_with(("127.0.0.1", 5999))
        assert second["context"]["already_running"] is True


class TestDevIntrospect:
    def test_introspect_lists_categories(self) -> None:
        mod = _load_script("introspect_hom.py")
        mock_hou = MagicMock()
        sop_cat = MagicMock()
        sop_cat.name.return_value = "Sop"
        mock_hou.sopNodeTypeCategory.return_value = sop_cat
        # Limit dir() to a known getter so the category scan is deterministic.
        with patch.dict(sys.modules, {"hou": mock_hou}), patch("builtins.dir", return_value=["sopNodeTypeCategory"]):
            result = mod.introspect_hom()
        assert result["success"] is True
        assert "Sop" in result["context"]["categories"]

    def test_introspect_target_members(self) -> None:
        mod = _load_script("introspect_hom.py")
        mock_hou = MagicMock()

        def _node(path):
            return None

        mock_hou.node = _node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.introspect_hom(target="hou.node")
        assert result["success"] is True
        assert result["context"]["callable"] is True
        assert result["context"]["signature"] == "(path)"


class TestDevUi:
    def test_ui_snapshot_headless(self) -> None:
        mod = _load_script("ui_snapshot.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.ui_snapshot()
        assert result["success"] is True
        assert result["context"]["supported"] is False

    def test_ui_action_headless(self) -> None:
        mod = _load_script("ui_action.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.ui_action("display_message", value="hi")
        assert result["success"] is True
        assert result["context"]["supported"] is False

    def test_ui_action_unsupported(self) -> None:
        mod = _load_script("ui_action.py")
        mock_hou = MagicMock()
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.ui_action("delete_everything")
        assert result["success"] is False
