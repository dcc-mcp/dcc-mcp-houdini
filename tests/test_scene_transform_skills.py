"""Unit tests for houdini-scene-edit and houdini-object-ops skills (issue #11).

No live Houdini is required; the HOM ``hou`` module is mocked per test.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(skill_name: str, script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"skill_{skill_name}_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _mock_node(path: str, name: str, type_name: str) -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = type_name
    return node


class TestSceneLifecycle:
    def test_new_scene_blocks_on_unsaved_changes(self) -> None:
        mod = _load_script("houdini-scene-edit", "new_scene.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.hipFile.hasUnsavedChanges.return_value = True

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.new_scene(force=False)

        assert result["success"] is False
        mock_hou.hipFile.hasUnsavedChanges.assert_called_once_with()
        mock_hou.hipFile.clear.assert_not_called()

    def test_new_scene_force_clears(self) -> None:
        mod = _load_script("houdini-scene-edit", "new_scene.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        mock_hou.hipFile.hasUnsavedChanges.return_value = True

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.new_scene(force=True)

        assert result["success"] is True
        mock_hou.hipFile.hasUnsavedChanges.assert_not_called()
        mock_hou.hipFile.clear.assert_called_once_with(suppress_save_prompt=True)

    def test_new_scene_requires_force_when_hython_dirty_state_is_unknown(self) -> None:
        mod = _load_script("houdini-scene-edit", "new_scene.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        mock_hou.hipFile.hasUnsavedChanges.return_value = True

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.new_scene(force=False)

        assert result["success"] is False
        assert result["message"] == "Scene dirty state unavailable"
        assert "force=true" in result["error"]
        mock_hou.hipFile.hasUnsavedChanges.assert_not_called()
        mock_hou.hipFile.clear.assert_not_called()

    def test_open_scene_requires_force_when_hython_dirty_state_is_unknown(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-scene-edit", "open_scene.py")
        hip = tmp_path / "shot.hip"
        hip.write_bytes(b"hip")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        mock_hou.hipFile.hasUnsavedChanges.return_value = True
        mock_hou.hipFile.path.return_value = str(hip)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.open_scene(str(hip), force=False)

        assert result["success"] is False
        assert result["message"] == "Scene dirty state unavailable"
        assert "force=true" in result["error"]
        mock_hou.hipFile.hasUnsavedChanges.assert_not_called()
        mock_hou.hipFile.load.assert_not_called()

    def test_new_scene_fails_closed_when_gui_dirty_probe_raises(self) -> None:
        mod = _load_script("houdini-scene-edit", "new_scene.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.hipFile.hasUnsavedChanges.side_effect = RuntimeError("probe failed")

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.new_scene(force=False)

        assert result["success"] is False
        assert result["message"] == "Scene dirty state unavailable"
        mock_hou.hipFile.clear.assert_not_called()

    def test_open_scene_still_blocks_real_gui_unsaved_changes(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-scene-edit", "open_scene.py")
        hip = tmp_path / "shot.hip"
        hip.write_bytes(b"hip")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.hipFile.hasUnsavedChanges.return_value = True

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.open_scene(str(hip), force=False)

        assert result["success"] is False
        mock_hou.hipFile.load.assert_not_called()

    def test_open_scene_force_loads_in_hython_with_suppressed_prompt(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-scene-edit", "open_scene.py")
        hip = tmp_path / "shot.hip"
        hip.write_bytes(b"hip")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        mock_hou.hipFile.path.return_value = str(hip)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.open_scene(str(hip), force=True)

        assert result["success"] is True
        mock_hou.hipFile.hasUnsavedChanges.assert_not_called()
        mock_hou.hipFile.load.assert_called_once_with(
            str(hip),
            suppress_save_prompt=True,
            ignore_load_warnings=False,
        )

    def test_save_scene_requires_path_when_never_saved(self) -> None:
        mod = _load_script("houdini-scene-edit", "save_scene.py")
        mock_hou = MagicMock()
        mock_hou.hipFile.hasFile.return_value = False

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.save_scene()

        assert result["success"] is False
        mock_hou.hipFile.save.assert_not_called()

    def test_save_scene_with_path(self) -> None:
        mod = _load_script("houdini-scene-edit", "save_scene.py")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = "/tmp/out.hip"

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.save_scene(file_path="/tmp/out.hip")

        assert result["success"] is True
        mock_hou.hipFile.save.assert_called_once_with(file_name="/tmp/out.hip")


class TestSelectionAndDiscovery:
    def test_set_selection_reports_missing(self) -> None:
        mod = _load_script("houdini-scene-edit", "set_selection.py")
        good = _mock_node("/obj/geo1", "geo1", "geo")
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: good if path == "/obj/geo1" else None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_selection(["/obj/geo1", "/obj/missing"])

        assert result["success"] is True
        mock_hou.clearAllSelected.assert_called_once()
        good.setSelected.assert_called_once_with(True)
        assert result["context"]["count"] == 1
        assert result["context"]["missing"] == ["/obj/missing"]

    def test_find_nodes_by_name_and_type(self) -> None:
        mod = _load_script("houdini-scene-edit", "find_nodes.py")
        box = _mock_node("/obj/geo1/box1", "box1", "box")
        sphere = _mock_node("/obj/geo1/sphere1", "sphere1", "sphere")
        root = MagicMock()
        root.allSubChildren.return_value = [box, sphere]
        mock_hou = MagicMock()
        mock_hou.node.return_value = root

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.find_nodes(name_pattern="box*", type_filter="box")

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["nodes"][0]["path"] == "/obj/geo1/box1"

    def test_list_cameras(self) -> None:
        mod = _load_script("houdini-scene-edit", "list_cameras.py")
        cam = _mock_node("/obj/cam1", "cam1", "cam")
        geo = _mock_node("/obj/geo1", "geo1", "geo")
        root = MagicMock()
        root.allSubChildren.return_value = [cam, geo]
        mock_hou = MagicMock()
        mock_hou.node.return_value = root

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_cameras()

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["cameras"][0]["name"] == "cam1"

    def test_get_bounding_box(self) -> None:
        mod = _load_script("houdini-scene-edit", "get_bounding_box.py")
        bbox = MagicMock()
        bbox.minvec.return_value = [0.0, 0.0, 0.0]
        bbox.maxvec.return_value = [1.0, 2.0, 3.0]
        bbox.sizevec.return_value = [1.0, 2.0, 3.0]
        bbox.center.return_value = [0.5, 1.0, 1.5]
        geo = MagicMock()
        geo.boundingBox.return_value = bbox
        node = _mock_node("/obj/geo1/box1", "box1", "box")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_bounding_box("/obj/geo1/box1")

        assert result["success"] is True
        assert result["context"]["max"] == [1.0, 2.0, 3.0]
        assert result["context"]["center"] == [0.5, 1.0, 1.5]


class TestObjectEdits:
    def test_rename_node(self) -> None:
        mod = _load_script("houdini-object-ops", "rename_node.py")
        node = _mock_node("/obj/geo1", "geo1", "geo")
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.rename_node("/obj/geo1", "hero")

        assert result["success"] is True
        node.setName.assert_called_once_with("hero", unique_name=True)

    def test_duplicate_node(self) -> None:
        mod = _load_script("houdini-object-ops", "duplicate_node.py")
        node = _mock_node("/obj/geo1", "geo1", "geo")
        copy = _mock_node("/obj/geo2", "geo2", "geo")
        parent = MagicMock()
        parent.copyItems.return_value = [copy]
        node.parent.return_value = parent
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.duplicate_node("/obj/geo1", new_name="clone")

        assert result["success"] is True
        parent.copyItems.assert_called_once_with([node])
        copy.setName.assert_called_once_with("clone", unique_name=True)

    def test_parent_node(self) -> None:
        mod = _load_script("houdini-object-ops", "parent_node.py")
        node = _mock_node("/obj/geo1", "geo1", "geo")
        new_parent = _mock_node("/obj/subnet1", "subnet1", "subnet")
        moved = _mock_node("/obj/subnet1/geo1", "geo1", "geo")
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: {"/obj/geo1": node, "/obj/subnet1": new_parent}.get(path)
        mock_hou.moveNodesTo.return_value = [moved]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.parent_node("/obj/geo1", "/obj/subnet1")

        assert result["success"] is True
        mock_hou.moveNodesTo.assert_called_once_with([node], new_parent)
        assert result["context"]["node"]["path"] == "/obj/subnet1/geo1"

    def test_set_node_flags(self) -> None:
        mod = _load_script("houdini-object-ops", "set_node_flags.py")
        node = _mock_node("/obj/geo1/box1", "box1", "box")
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_node_flags("/obj/geo1/box1", display=True, bypass=False)

        assert result["success"] is True
        node.setDisplayFlag.assert_called_once_with(True)
        node.bypass.assert_called_once_with(False)
        assert result["context"]["applied"] == {"display": True, "bypass": False}

    def test_set_node_lock(self) -> None:
        mod = _load_script("houdini-object-ops", "set_node_lock.py")
        node = _mock_node("/obj/geo1/box1", "box1", "box")
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_node_lock("/obj/geo1/box1", locked=True)

        assert result["success"] is True
        node.setHardLocked.assert_called_once_with(True)


class TestTransforms:
    def test_get_transform(self) -> None:
        mod = _load_script("houdini-object-ops", "get_transform.py")
        node = _mock_node("/obj/geo1", "geo1", "geo")

        def _parm_tuple(name):
            values = {"t": [1.0, 2.0, 3.0], "r": [0.0, 90.0, 0.0], "s": [1.0, 1.0, 1.0]}
            if name not in values:
                return None
            pt = MagicMock()
            pt.eval.return_value = values[name]
            return pt

        node.parmTuple.side_effect = _parm_tuple
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_transform("/obj/geo1")

        assert result["success"] is True
        assert result["context"]["translate"] == [1.0, 2.0, 3.0]
        assert result["context"]["rotate"] == [0.0, 90.0, 0.0]

    def test_set_transform(self) -> None:
        mod = _load_script("houdini-object-ops", "set_transform.py")
        node = _mock_node("/obj/geo1", "geo1", "geo")
        t_tuple = MagicMock()
        node.parmTuple.side_effect = lambda name: t_tuple if name == "t" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_transform("/obj/geo1", translate=[5, 0, 0], rotate=[0, 0, 0])

        assert result["success"] is True
        t_tuple.set.assert_called_once_with((5, 0, 0))
        assert result["context"]["applied"]["t"] == [5.0, 0.0, 0.0]
        assert result["context"]["unsupported"] == ["r"]
