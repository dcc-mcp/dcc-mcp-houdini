"""Proposed acceptance tests for fail-closed remove_hda_definition guard.

These encode the behavior member hallong requested (PIP-4975 follow-up):
  1) node_type_instances() returns None on enumeration failure (unknown), not [].
  2) remove_hda_definition() refuses destroy() when instance state is unknown and
     allow_orphan_instances is False.
  4) dry_run=true with hda_file must not install the library nor switch active def.

Status against PR #349 head 45e2311: RED (documents the defects). They should
turn GREEN after the fail-closed fix.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_AUTO = _SKILLS_ROOT / "houdini-hda-automation" / "scripts"


def _load(script_name: str) -> ModuleType:
    path = _AUTO / script_name
    spec = importlib.util.spec_from_file_location(f"acc_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _node(path: str) -> MagicMock:
    n = MagicMock()
    n.path.return_value = path
    return n


class _RemovalFixture:
    def __init__(self, node_type_name="studio::solar", library="/assets/solar.hda"):
        self.destroyed = False
        self.install_calls = []
        category = MagicMock()
        category.name.return_value = "Sop"
        self.node_type = MagicMock()
        self.node_type.name.return_value = node_type_name
        self.node_type.category.return_value = category
        self.definition = MagicMock()
        self.definition.nodeTypeName.return_value = node_type_name
        self.definition.libraryFilePath.return_value = library
        self.definition.version.return_value = "1.0"
        self.definition.description.return_value = "Solar"
        self.definition.isCurrent.return_value = True
        self.definition.isInstalled.return_value = True
        self.definition.sections.return_value = {}
        self.definition.nodeType.return_value = self.node_type
        self.node_type.definition.return_value = self.definition

        def destroy():
            self.destroyed = True

        self.definition.destroy.side_effect = destroy
        self.mock_hou = MagicMock()
        self.mock_hou.nodeType.side_effect = lambda _c, _n: None if self.destroyed else self.node_type
        self.mock_hou.hda.installFile.side_effect = lambda p: self.install_calls.append(p)


# ---- point 1: node_type_instances fail-closed contract ----
class TestNodeTypeInstancesFailClosed:
    def test_returns_none_when_instances_raises(self):
        common = _load("_hda_auto_common.py")
        nt = MagicMock()
        nt.instances.side_effect = RuntimeError("enumerate failed")
        assert common.node_type_instances(nt) is None

    def test_returns_none_when_instances_not_callable(self):
        common = _load("_hda_auto_common.py")
        nt = MagicMock()
        nt.instances = None
        assert common.node_type_instances(nt) is None

    def test_returns_none_when_any_path_read_fails(self):
        common = _load("_hda_auto_common.py")
        bad = _node("/obj/geo1/x")
        bad.path.side_effect = RuntimeError("path read failed")
        nt = MagicMock()
        nt.instances.return_value = [bad, _node("/obj/geo2/y")]
        assert common.node_type_instances(nt) is None

    def test_returns_empty_list_only_when_confirmed_zero(self):
        common = _load("_hda_auto_common.py")
        nt = MagicMock()
        nt.instances.return_value = []
        assert common.node_type_instances(nt) == []


# ---- point 2: remove_hda_definition refuses destroy when state unknown ----
class TestRemoveRefusesUnknownState:
    def test_refuses_when_instances_raises(self):
        mod = _load("remove_hda_definition.py")
        fx = _RemovalFixture()
        fx.node_type.instances.side_effect = RuntimeError("enumerate failed")
        with patch.dict(sys.modules, {"hou": fx.mock_hou}):
            result = mod.remove_hda_definition("studio::solar")
        assert result["success"] is False
        fx.definition.destroy.assert_not_called()

    def test_refuses_when_instances_not_callable(self):
        mod = _load("remove_hda_definition.py")
        fx = _RemovalFixture()
        fx.node_type.instances = None
        with patch.dict(sys.modules, {"hou": fx.mock_hou}):
            result = mod.remove_hda_definition("studio::solar")
        assert result["success"] is False
        fx.definition.destroy.assert_not_called()

    def test_allows_when_unknown_but_orphan_explicit(self):
        mod = _load("remove_hda_definition.py")
        fx = _RemovalFixture()
        fx.node_type.instances.side_effect = RuntimeError("enumerate failed")
        with patch.dict(sys.modules, {"hou": fx.mock_hou}):
            result = mod.remove_hda_definition("studio::solar", allow_orphan_instances=True)
        assert result["success"] is True
        fx.definition.destroy.assert_called_once_with()

    def test_still_allows_confirmed_zero_instances(self):
        mod = _load("remove_hda_definition.py")
        fx = _RemovalFixture()
        fx.node_type.instances.return_value = []
        with patch.dict(sys.modules, {"hou": fx.mock_hou}):
            result = mod.remove_hda_definition("studio::solar")
        assert result["success"] is True
        fx.definition.destroy.assert_called_once_with()


# ---- point 5: dry_run with hda_file must not install or switch active def ----
class TestDryRunIsolation:
    def test_dry_run_hda_file_does_not_install(self):
        mod = _load("remove_hda_definition.py")
        fx = _RemovalFixture(library="/assets/solar.hda")
        fx.node_type.instances.return_value = []
        with patch.dict(sys.modules, {"hou": fx.mock_hou}):
            result = mod.remove_hda_definition("studio::solar", hda_file="/assets/solar.hda", dry_run=True)
        assert result["success"] is True
        assert result["context"]["dry_run"] is True
        fx.mock_hou.hda.installFile.assert_not_called()
        fx.definition.destroy.assert_not_called()
